import pprint
import pandas as pd
from itertools import combinations
import statsmodels.formula.api as sm
from psycopg2.extras import Json
from sklearn.linear_model import LinearRegression
from scipy.stats import chisquare, mode
from numpy import percentile, mean
from time import time
from capexplain.pattern_miner.permtest import *
from capexplain.fd.fd import closure

# ********************************************************************************
class MinerConfig:
    """
    MinerConfig - configuration for the pattern mining algorithm
    """
    conn=None
    table=None
    theta_c=None #theta for constant regression
    theta_l=None #theta for linear regression
    lamb=None #lambda
    #c_star=False
    #pc=None
    fit=None #if we are fitting model
    dist_thre=None #threshold for identifying distinct-value attributes
    reg_package=None #statsmodels or sklearn
    supp_l=None #local support
    supp_g=None #global support
    fd_check=None #toggle on/off functional dependency checks
    supp_inf=None #toggle on/off support inference rules
    algorithm=None #{'optimized','naive','naive_alternative'}

    def __init__(self,
                 conn=None,
                 table=None,
                 fit=True,
                 theta_c=0.5,
                 theta_l=0.5,
                 lamb=0.5,
                 dist_thre=0.99,
                 reg_package='statsmodels',
                 supp_l=10,
                 supp_g=100,
                 fd_check=True,
                 supp_inf=True,
                 algorithm='optimized'):
        self.conn=conn
        self.theta_c=theta_c
        self.theta_l=theta_l
        self.lamb=lamb
        self.fit=fit
        self.dist_thre=dist_thre
        self.reg_package=reg_package
        self.supp_l=supp_l
        self.supp_g=supp_g
        self.fd_check=fd_check
        self.supp_inf=supp_inf
        self.algorithm=algorithm
        self.table=table

    def validateConfiguration(self):
        if reg_package not in {'statsmodels','sklearn'}:
            print('Invalid input for reg_package, reset to default')
            reg_package='statsmodels'
        if algorithm not in {'naive','naive_alternative','optimized'}:
            print('Invalid input for algorithm, reset to default')
            algorithm='optimized'
        return True

    def printConfig(self):
        pprint.pprint(self.__dict__)

# ********************************************************************************
class MinerStats:
    """
    Statistics gathered during mining
    """

    time=None

    def __init__():
        time={'aggregate':0,
              'df':0,
              'regression':0,
              'insertion':0,
              'drop':0,
              'loop':0,
              'innerloop':0,
              'fd_detect':0,
              'check_fd':0,
              'total':0}



# ********************************************************************************
class PatternFinder:
    """
    Mining patterns for an input relation. Patterns are stored in a table X
    """

    config=None
    stats=None

    fd=[] #functional dependencies
    glob=[] #global patterns
    num_rows=None #number of rows of config.table
    cat=None #categorical attributes
    num=None #numeric attributes
    n=None#number of attributes
    attr_index={} #index of all attributes
    grouping_attr=None #attributes can be in group
    schema=None #list of all attributes
    time=None #record running time for each section
    superkey=None #used to track compound key
    failedf=None #used to apply support inference
    
    def __init__(self, config : MinerConfig):
        self.config = config
        self.initDataStructures()
        try:
            self.schema=list(pd.read_sql("SELECT * FROM "+config.table+" LIMIT 1",config.conn))
        except Exception as ex:
            print(ex)
        
        self.n=len(self.schema)
        for i in range(self.n):
            self.attr_index[self.schema[i]]=i

        self.num_rows=pd.read_sql("SELECT count(*) as num from "+config.table,config.conn)['num'][0]
#         self.fd={}
        #check uniqueness, grouping_attr contains only non-unique attributes
        unique=pd.read_sql("SELECT attname,n_distinct FROM pg_stats WHERE tablename='"+table+"'",config.conn)
        for tup in unique.itertuples():
            if (tup.n_distinct<0 and tup.n_distinct > -config.dist_thre) or \
            (tup.n_distinct>0 and tup.n_distinct<self.num_rows*config.dist_thre):
                self.grouping_attr.append(tup.attname)
                
        for col in self.schema:
#             if col=='year':
#                 self.num.append(col)
#             elif col!='id':
#                 self.cat.append(col)
            try: # Boris: this may fail, better to get the datatype from the catalog and have a list of numeric datatypes to check for
                config.conn.execute("SELECT CAST("+col+" AS NUMERIC) FROM "+config.table)
                self.num.append(col)
            except:
                self.cat.append(col)

    def initDataStructures():
        self.stats = MinerStats()
        self.superkey=set()        
        self.cat=[]
        self.num=[]
        self.grouping_attr=[]
                
    def addFd(self, fd):
        '''
        type fd:list of size-2 tuples, tuple[0]=list of lhs attributes and tuple[1]=list of rhs attributes
        '''
        if not config.fd_check: #if toggle is off, not adding anything
            return
        for tup in fd:
            for i in range(2):
                for j in range(len(tup[i])):
                    try:
                        tup[i][j]=self.attr_index[tup[i][j]]
                    except KeyError as ex:
                        print(str(ex)+" is not in the table")
                        raise ex
        self.fd.extend(fd)
        
    def validateFd(self,group,division=None):
        '''
        check if we want to ignore f=group[:division], v=group[division:]
        type group: tuple of strings
        
        return True if group is valid
        return False if we decide to ignore it
        
        if division=None, check all possible divisions, and return boolean[]
        '''
        if division:
            f=set()# indices of fixed attributes
            attrs=set()# indices of all attributes
            for i in range(len(group)):
                if i<division:
                    f.add(self.attr_index[group[i]])
                attrs.add(self.attr_index[group[i]])
                
            for i in range(len(group)):
                cur=self.attr_index[group[i]]
                if i<division: #group[i] in f
                    if cur in closure(self.fd,self.n,f-{cur}):
                        return False
                else: #group[i] in v
                    if cur in closure(self.fd,self.n,attrs-{cur}):
                        return False
                    
            return True
        else:
            n=len(group)
            ret=[self.validateFd(group,i) for i in range(1,n)] #division from 1 to n-1
            return ret
            
    def findPattern(self,user=None):
#       self.pc=PC.PatternCollection(list(self.schema))
        self.glob=[]#reset self.glob
        self.createTable()
        start=time()
        if not user:
            grouping_attr=self.grouping_attr
            aList=self.num+['*']
            
        else:
            grouping_attr=user['group']
            aList=user['a']
        
        for a in aList:
            if not user:
                if a=='*':#For count, only do a count(*)
                    agg="count"
                else: #a in self.num
                    agg="sum"
            else:
                agg=user['agg']
            #for agg in aggList :
            cols=[col for col in grouping_attr if col!=a]
            n=len(cols)
            if config.algorithm=='naive':
                self.formCube(a, agg, cols)
                for size in range(min(4,n),1,-1):
                    combs=combinations(cols,size)
                    for group in combs:#comb=f+v
                        for fsize in range(1,len(group)):
                            fs=combinations(group,fsize)
                            for f in fs:
                                self.fit_naive(f,group,a,agg,cols)
                self.dropCube()
            else:#config.algorithm=='optimized' or config.algorithm=='naive_alternative'
                combs=combinations([i for i in range(n)],min(4,n))
                for comb in combs:
                    grouping=[cols[i] for i in comb]
                    self.aggQuery(grouping,a,agg)
                    perms=permutations(comb,len(comb))
                    for perm in perms:
                        self.failedf=set()#reset failed f for each permutation
                        #check if perm[0]->perm[1], if so, ignore whole group
                        if perm[1] in closure(self.fd,self.n,[perm[0]]):
                            continue
                        
                        decrease=0
                        d_index=None
                        division=None
                        for i in range(1,len(perm)):
                            if perm[i-1]>perm[i]:
                                decrease+=1
                                if decrease==1:
                                    division=i #f=group[:divition],v=group[division:] is the only division
                                elif decrease==2:
                                    d_index=i #perm[:d_index] will decrease at most once
                                    break
            
                        if not d_index:
                            d_index=len(perm)
                            pre=findpre(perm,d_index-1,n)#perm[:pre] are taken care of by other grouping
                        else:
                            pre=findpre(perm,d_index,n)
                            
                        if pre==d_index:
                            continue
                        else:
                            group=tuple([cols[i] for i in perm])
                            self.rollupQuery(group, pre, d_index, agg)
                            
                            fd_detect_start=time()
                            if config.fd_check==True:
                                prev_rows=None
                                for j in range(pre,d_index+1):#first loop is to set prev_rows
                                    condition=' and '.join(['g_'+group[k]+'=0' if k<j else 'g_'+group[k]+'=1'
                                                            for k in range(d_index)])
                                    cur_rows=pd.read_sql('SELECT count(*) as num FROM grouping WHERE '+condition,
                                                   con=config.conn)['num'][0]
                                    if prev_rows:
                                        if cur_rows>=self.num_rows*config.dist_thre:
                                            d_index=j-1 #group[:j] will be distinct value groups (superkey)
                                            #self.addFd([group[:j-1],group[j-1]])
                                            self.superkey.add(group[:j])
                                            break
                                        elif prev_rows>=cur_rows*config.dist_thre:
                                            d_index=j-1#group[:j-1] implies group[j-1]
                                            self.addFd([(list(group[:j-1]),[group[j-1]])])
                                            break
                                    prev_rows=cur_rows
                            stats.time['fd_detect']+=time()-fd_detect_start
                                
                            for j in range(d_index,pre,-1):
                                prefix=group[:j]
                                
                                #check if group contains superkey
                                for i in self.superkey:
                                    if set(prefix).issubset(i):
                                        break
                                else:# if contains superkey, go to next j
                                    if division and division>=j:
                                        division=None
                                        
                                    #check functional dependency here if division exists, otherwise check in fit
                                    check_fd_start=time()
                                    if division and not self.validateFd(prefix,division):
                                        continue
                                    stats.time['check_fd']+=time()-check_fd_start
                                    
                                    condition=' and '.join(['g_'+group[k]+'=0' if k<j else 'g_'+group[k]+'=1'
                                                            for k in range(d_index)])
                                    df_start=time()                              
                                    df=pd.read_sql('SELECT '+','.join(prefix)+','+agg+' FROM grouping WHERE '+condition,
                                                   con=config.conn)
                                    stats.time['df']+=time()-df_start                                
                                    self.fitmodel(df,prefix,a,agg,division)
                            self.dropRollup()
                    self.dropAgg()    
        if self.glob:
            insert_start=time()
            config.conn.execute("INSERT INTO "+config.table+"_global values"+','.join(self.glob))
            stats.time['insertion']+=time()-insert_start
        stats.time['total']=time()-start
        self.insertTime(str(len(self.glob)))
        
        
    def formCube(self, a, agg, attr):
        group=",".join(["CAST("+num+" AS NUMERIC)" for num in attr if num in self.num]+
                        [cat for cat in attr if cat not in self.num])
        grouping=",".join(["CAST("+num+" AS NUMERIC), GROUPING(CAST("+num+" AS NUMERIC)) as g_"+num
                        for num in attr if num in self.num]+
            [cat+", GROUPING("+cat+") as g_"+cat for cat in attr if cat not in self.num])
        if a in self.num:
            a="CAST("+a+" AS NUMERIC)"
        config.conn.execute("DROP TABLE IF EXISTS cube")
        query="CREATE TABLE cube AS SELECT "+agg+"("+a+"), "+grouping+" FROM "+config.table+" GROUP BY CUBE("+group+")"
        config.conn.execute(query)        
     
    def dropCube(self):
        config.conn.execute("DROP TABLE cube;")
        
    def cubeQuery(self, g, f, cols):
        #=======================================================================
        # res=" and ".join([a+".notna()" for a in g])
        # if len(g)<len(cols):
        #     null=" and ".join([b+".isna()" for b in cols if b not in g])
        #     res=res+" and "+null
        #=======================================================================
        res=" and ".join(["g_"+a+"=0" for a in g])
        if len(g)<len(cols):
            unused=" and ".join(["g_"+b+"=1" for b in cols if b not in g])
            res=res+" and "+unused
        return "SELECT * FROM cube where "+res+" ORDER BY "+",".join(f)
    
    def fit_naive(self,f,group,a,agg,cols):
        self.failedf=set()#to not trigger error
        fd=pd.read_sql(self.cubeQuery(group, f, cols),config.conn)
        g=tuple([att for att in f]+[attr for attr in group if attr not in f])
        division=len(f)
        self.fitmodel_with_division(fd, g, a, agg, division)
        
    def findPattern_inline(self,group,a,agg):
        #loop through permutations of group
        user={'group':group,'a':[a],'agg':agg}
        self.findPattern(user)
        
    def aggQuery(self, g, a, agg):
        start=time()
        group=",".join(["CAST("+att+" AS NUMERIC)" if att in self.num else att for att in g])
        if agg=='sum':
            a='CAST('+a+' AS NUMERIC)'
        query="CREATE TEMP TABLE agg as SELECT "+group+","+agg+"("+a+")"+" FROM "+config.table+" GROUP BY "+group
        config.conn.execute(query)
        stats.time['aggregate']+=time()-start
    
    def rollupQuery(self, group, pre, d_index, agg):
        start=time()
        grouping=",".join([attr+", GROUPING("+attr+") as g_"+attr for attr in group[:d_index]])
#        gsets=','.join(['('+','.join(group[:prefix])+')' for prefix in range(d_index,pre,-1)])
        config.conn.execute('CREATE TEMP TABLE grouping AS '+
                        'SELECT '+grouping+', SUM('+agg+') as '+agg+
#                        ' FROM agg GROUP BY GROUPING SETS('+gsets+')'+
                        ' FROM agg GROUP BY ROLLUP('+','.join(group)+')'+
                        ' ORDER BY '+','.join(group[:d_index]))
        stats.time['aggregate']+=time()-start
        
    def dropRollup(self):
        drop_start=time()
        config.conn.execute('DROP TABLE grouping')
        stats.time['drop']+=time()-drop_start
        
    def dropAgg(self):
        drop_start=time()
        config.conn.execute('DROP TABLE agg')
        self.time['drop']+=time()-drop_start
        
    def fitmodel(self, fd, group, a, agg, division):
        loop_start=time()
        if division:
            self.fitmodel_with_division(fd, group, a, agg, division)
        else:
            self.fitmodel_no_division(fd, group, a, agg)
        self.time['loop']+=time()-loop_start
            
    def fitmodel_no_division(self, fd, group, a, agg):
        size=len(group)-1
        oldKey=None
        oldIndex=[0]*size
        num_f=[0]*size
        valid_l_f=[0]*size
        valid_c_f=[0]*size
        f=[list(group[:i]) for i in range(1,size+1)]
        v=[list(group[j:]) for j in range(1,size+1)]
        supp_valid=[group[:i] not in self.failedf for i in range(1,size+1)]
        f_dict=[{} for i in range(1,size+1)]
        check_fd_start=time()
        fd_valid=self.validateFd(group)
        self.time['check_fd']+=time()-check_fd_start
        
        if not any(fd_valid) or not any(supp_valid):
            return
        pattern=[]
        def fit(df,fval,i,n):
            if not config.fit:
                return
            reg_start=time()
            describe=[mean(df[agg]),mode(df[agg]),percentile(df[agg],25)
                      ,percentile(df[agg],50),percentile(df[agg],75)]
                                
            #fitting constant
            theta_c=chisquare(df[agg])[1]
            if theta_c>config.theta_c:
                nonlocal valid_c_f
                valid_c_f[i]+=1
                #self.pc.add_local(f,oldKey,v,a,agg,'const',theta_c)
                pattern.append(self.addLocal(f[i],fval,v[i],a,agg,'const',theta_c,describe,'NULL'))
              
            #fitting linear
            if  theta_c!=1 and ((config.reg_package=='sklearn' and all(attr in self.num for attr in v[i])
                                or
                                (config.reg_package=='statsmodels' and any(attr in self.num for attr in v[i])))):

                if config.reg_package=='sklearn':   
                    lr=LinearRegression()
                    lr.fit(df[v[i]],df[agg])
                    theta_l=lr.score(df[v[i]],df[agg])
                    theta_l=1-(1-theta_l)*(n-1)/(n-len(v[i])-1)
                    param=lr.coef_.tolist()
                    param.append(lr.intercept_.tolist())
                    param="'"+str(param)+"'"
                else: #statsmodels
                    lr=sm.ols(agg+'~'+'+'.join(v[i]),data=df,missing='drop').fit()
                    theta_l=lr.rsquared_adj
                    param=Json(dict(lr.params))
                
                if theta_l and theta_l>config.theta_l:
                    nonlocal valid_l_f
                    valid_l_f[i]+=1
                #self.pc.add_local(f,oldKey,v,a,agg,'linear',theta_l)
                    pattern.append(self.addLocal(f[i],fval,v[i],a,agg,'linear',theta_l,describe,param))
                    
            self.time['regression']+=time()-reg_start
            
        inner_loop_start=time()
 
        for tup in fd.itertuples():
            
            position=None
            if oldKey:
                for i in range(size):
                    if getattr(tup,group[i])!=getattr(oldKey,group[i]):
                        position=i
                        break 
            
            if position is not None:
                index=tup.Index
                for i in range(position,size):
#                     make_reference=time()
#                     temp=fd[oldIndex[i]:index].copy()
#                     self.time['make_reference']+=time()-make_reference
                    if not fd_valid[i] or not supp_valid[i]:
                        continue
                    n=index-oldIndex[i]
                    if n>=config.supp_l:
                        num_f[i]+=1
                        fval=tuple([getattr(oldKey,j) for j in f[i]])
                        f_dict[i][fval]=[oldIndex[i],index]
                        #fit(fd[oldIndex[i]:index],fval,i,n)
                    oldIndex[i]=index
                    
            oldKey=tup
            
        if oldKey:
            for i in range(size):
#                 make_reference=time()
#                 temp=fd[oldIndex[i]:].copy()
#                 self.time['make_reference']+=time()-make_reference
                if not fd_valid[i] or not supp_valid[i]:
                    continue
                n=oldKey.Index-oldIndex[i]+1
                if n>config.supp_l:
                    num_f[i]+=1
                    fval=tuple([getattr(oldKey,j) for j in f[i]])
                    f_dict[i][fval]=[oldIndex[i]]
                    #fit(fd[oldIndex[i]:],fval,i,n)
        self.time['innerloop']+=time()-inner_loop_start
        
        for i in range(size):
            if len(f_dict[i])<config.supp_g:
                if config.supp_inf:#if toggle is on
                    self.failedf.add(tuple(f[i]))
                supp_valid[i]=False
            else:
                for fval in f_dict[i]:
                    indices=f_dict[i][fval]
                    if len(indices)==2: #indices=[oldIndex,index]
                        fit(fd[indices[0]:indices[1]],fval,i,indices[1]-indices[0])
                    else: #indices=[oldIndex]
                        fit(fd[indices[0]:],fval,i,oldKey.Index-indices[0]+1)
                    
        #sifting global            
        for i in range(size):
            if not fd_valid[i] or not supp_valid[i]:
                    continue
            if num_f[i]>config.supp_g:
                lamb_c=valid_c_f[i]/num_f[i]
                lamb_l=valid_l_f[i]/num_f[i]
                if lamb_c>config.lamb:
                    #self.pc.add_global(f,v,a,agg,'const',config.theta_c,lamb_c)
                    self.glob.append(self.addGlobal(f[i],v[i],a,agg,'const',config.theta_c,lamb_c))
                if lamb_l>config.lamb:
                    #self.pc.add_global(f,v,a,agg,'linear',str(config.theta_l),str(lamb_l))
                    self.glob.append(self.addGlobal(f[i],v[i],a,agg,'linear',config.theta_l,lamb_l))
        
        if not config.fit:
            return 
        
        '''
        #adding local with f=empty set
        if not self.validateFd(group,0):
            return
        reg_start=time()
        describe=[mean(fd[agg]),mode(fd[agg]),percentile(fd[agg],25)
                                          ,percentile(fd[agg],50),percentile(fd[agg],75)]
                           
        #fitting constant
        theta_c=chisquare(fd[agg])[1]
        if theta_c>config.theta_c:
            pattern.append(self.addLocal([' '],[' '],group,a,agg,'const',theta_c,describe,'NULL'))
          
          
                    
        #fitting linear
        if  theta_c!=1 and ((config.reg_package=='sklearn' and all(attr in self.num for attr in group)
                            or
                            (config.reg_package=='statsmodels' and any(attr in self.num for attr in group)))):
            
            gl=list(group)
            if config.reg_package=='sklearn':
                lr=LinearRegression()
                lr.fit(fd[gl],fd[agg])
                theta_l=lr.score(fd[gl],fd[agg])
                n=len(fd)
                theta_l=1-(1-theta_l)*(n-1)/(n-len(group)-1)
                param=lr.coef_.tolist()
                param.append(lr.intercept_.tolist())
                param="'"+str(param)+"'"
            else: #statsmodels
                lr=sm.ols(agg+'~'+'+'.join(gl),data=fd,missing='drop').fit()
                theta_l=lr.rsquared_adj
                param=Json(dict(lr.params))
            
            if theta_l and theta_l>config.theta_l:
            #self.pc.add_local(f,oldKey,v,a,agg,'linear',theta_l)
                pattern.append(self.addLocal([' '],[' '],group,a,agg,'linear',theta_l,describe,param))
        self.time['regression']+=time()-reg_start
        '''
        
        if pattern:
            insert_start=time()
            config.conn.execute("INSERT INTO "+config.table+"_local values"+','.join(pattern))        
            self.time['insertion']+=time()-insert_start
    def fitmodel_with_division(self, fd, group, a, agg, division): 
        #fd=d.sort_values(by=f).reset_index(drop=True)
        
        #check global support inference
        if group[:division] in self.failedf:
            return
        
        oldKey=None
        oldIndex=0
        num_f=0
        valid_l_f=0
        valid_c_f=0
        f=list(group[:division])
        v=list(group[division:])  
        #df:dataframe n:length    
        pattern=[]
        def fit(df,f,fval,v,n):
            if not config.fit:
                return
            reg_start=time()
            describe=[mean(df[agg]),mode(df[agg]),percentile(df[agg],25)
                                          ,percentile(df[agg],50),percentile(df[agg],75)]
                                
            #fitting constant
            theta_c=chisquare(df[agg])[1]
            if theta_c>config.theta_c:
                nonlocal valid_c_f
                valid_c_f+=1
                #self.pc.add_local(f,oldKey,v,a,agg,'const',theta_c)
                pattern.append(self.addLocal(f,fval,v,a,agg,'const',theta_c,describe,'NULL'))
                
            #fitting linear
            if  theta_c!=1 and ((config.reg_package=='sklearn' and all(attr in self.num for attr in v)
                                or
                                (config.reg_package=='statsmodels' and any(attr in self.num for attr in v)))):

                if config.reg_package=='sklearn': 
                    lr=LinearRegression()
                    lr.fit(df[v],df[agg])
                    theta_l=lr.score(df[v],df[agg])
                    theta_l=1-(1-theta_l)*(n-1)/(n-len(v)-1)
                    param=lr.coef_.tolist()
                    param.append(lr.intercept_.tolist())
                    param="'"+str(param)+"'"
                else: #statsmodels
                    lr=sm.ols(agg+'~'+'+'.join(v),data=df,missing='drop').fit()
                    theta_l=lr.rsquared_adj
                    param=Json(dict(lr.params))
                    
                if theta_l and theta_l>config.theta_l:
                    nonlocal valid_l_f
                    valid_l_f+=1
                #self.pc.add_local(f,oldKey,v,a,agg,'linear',theta_l)
                    pattern.append(self.addLocal(f,fval,v,a,agg,'linear',theta_l,describe,param))
                    
            self.time['regression']+=time()-reg_start
        
        inner_loop_start=time()
        change=False
        f_dict={}
        for tup in fd.itertuples():
            if oldKey:
                change=any([getattr(tup,attr)!=getattr(oldKey,attr) for attr in f])
            if change:
                index=tup.Index
#                 make_reference=time()
#                 temp=fd[oldIndex:index].copy()
#                 self.time['make_reference']+=time()-make_reference
                n=index-oldIndex
                if n>=config.supp_l:
                    num_f+=1
                    #fit(fd[oldIndex:index],f,v,n)
                    fval=tuple([getattr(oldKey,j) for j in f])
                    f_dict[fval]=[oldIndex,index]
                oldIndex=index
            oldKey=tup
            
        if oldKey:
#             make_reference=time()
#             temp=fd[oldIndex:].copy()
#             self.time['make_reference']+=time()-make_reference
            n=oldKey.Index-oldIndex+1
            if n>=config.supp_l:
                num_f+=1
                #fit(fd[oldIndex:],f,v,n)
                fval=tuple([getattr(oldKey,j) for j in f])
                f_dict[fval]=[oldIndex]
        self.time['innerloop']+=time()-inner_loop_start
        
        if len(f_dict)<config.supp_g:
            if config.supp_inf:#if toggle is on
                self.failedf.add(group[:division])
            return
        else:
            for fval in f_dict:
                indices=f_dict[fval]
                if len(indices)==2: #indices=[oldIndex,index]
                    fit(fd[indices[0]:indices[1]],f,fval,v,indices[1]-indices[0])
                else: #indices=[oldIndex]
                    fit(fd[indices[0]:],f,fval,v,oldKey.Index-indices[0]+1)
        
        if pattern:
            insert_start=time()
            config.conn.execute("INSERT INTO "+config.table+"_local values"+','.join(pattern))
            self.time['insertion']+=time()-insert_start
        
        if num_f>config.supp_g:
            lamb_c=valid_c_f/num_f
            lamb_l=valid_l_f/num_f
            if lamb_c>config.lamb:
                #self.pc.add_global(f,v,a,agg,'const',config.theta_c,lamb_c)
                self.glob.append(self.addGlobal(f,v,a,agg,'const',config.theta_c,lamb_c))
            if lamb_l>config.lamb:
                #self.pc.add_global(f,v,a,agg,'linear',str(config.theta_l),str(lamb_l))
                self.glob.append(self.addGlobal(f,v,a,agg,'linear',config.theta_l,lamb_l))
                          
    def addLocal(self,f,f_val,v,a,agg,model,theta,describe,param):
        f="'"+str(f).replace("'","")+"'"
        f_val="'"+str(f_val).replace("'","")+"'"
        v="'"+str(v).replace("'","")+"'"
        a="'"+a+"'"
        agg="'"+agg+"'"
        model="'"+model+"'"
        theta="'"+str(theta)+"'"
        describe="'"+str(describe).replace("'","")+"'"
        #return 'insert into '+config.table+'_local values('+','.join([f,f_val,v,a,agg,model,theta,describe,param])+');'
        return '('+','.join([f,f_val,v,a,agg,model,theta,describe,str(param)])+')'
    
    
    def addGlobal(self,f,v,a,agg,model,theta,lamb):
        f="'"+str(f).replace("'","")+"'"
        v="'"+str(v).replace("'","")+"'"
        a="'"+a+"'"
        agg="'"+agg+"'"
        model="'"+model+"'"
        theta="'"+str(theta)+"'"
        lamb="'"+str(lamb)+"'"
        #return 'insert into '+config.table+'_global values('+','.join([f,v,a,agg,model,theta,lamb])+');'
        return '('+','.join([f,v,a,agg,model,theta,lamb])+')'
         
    
    def createTable(self):
        config.conn.execute('DROP TABLE IF EXISTS '+config.table+'_local;')
        if config.reg_package=='sklearn':
            type='varchar'
        else:
            type='json'
            
        config.conn.execute('create table IF NOT EXISTS '+config.table+'_local('+
                     'fixed varchar,'+
                     'fixed_value varchar,'+
                     'variable varchar,'+
                     'in_a varchar,'+
                     'agg varchar,'+
                     'model varchar,'+
                     'theta float,'+
                     'stats varchar,'+
                     'param '+type+');')
        
        config.conn.execute('DROP TABLE IF EXISTS '+config.table+'_global')
        config.conn.execute('create table IF NOT EXISTS '+config.table+'_global('+
                     'fixed varchar,'+
                     'variable varchar,'+
                     'in_a varchar,'+
                     'agg varchar,'+
                     'model varchar,'+
                     'theta float,'+
                     'lambda float);')
        
        attr=''
        for key in self.time:
            attr+=key+' varchar,'
        config.conn.execute('create table IF NOT EXISTS time_detail_fd('+
                          'id serial primary key,'+
                          attr+
                          'description varchar);')
        
        
    def insertTime(self,description):
        attributes=list(self.time)
        values=[str(self.time[i]) for i in attributes]
        attributes.append('description')
        values.append(description)
        config.conn.execute('INSERT INTO time_detail_fd('+','.join(attributes)+') values('+','.join(values)+')')
