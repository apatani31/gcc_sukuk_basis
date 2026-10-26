import pandas as pd, numpy as np, statsmodels.formula.api as smf
d=pd.read_parquet('data/USD/analysis/twin_basis_obs.parquet')
d=d[d.parent_name!='Emirates']
u=pd.read_parquet('data/market/ust_curve.parquet').astype(float).ffill(limit=5)
ten=np.array(u.columns,dtype=float)
u.index=pd.to_datetime(u.index)
d['date']=pd.to_datetime(d['date'])
d=d[d.date.isin(u.index)]
U=u.loc[d.date].to_numpy()
def interp(row,t):
    m=~np.isnan(row); 
    return np.interp(t,ten[m],row[m]) if m.sum()>=2 else np.nan
d['ust']=[interp(r,t) for r,t in zip(U,d.tau.to_numpy())]
d['spread_bp']=(d.y_conv-d.ust)*100
d=d.dropna(subset=['spread_bp'])
d['month']=d.date.dt.to_period('M')
iss=d.groupby('parent_name').agg(basis=('basis_bp','mean'),spread=('spread_bp','mean'),n=('basis_bp','size')).sort_values('spread')
print(iss.round(1))
print('cross-issuer corr(mean basis, mean spread):',iss.basis.corr(iss.spread).round(2), ' spearman', iss.basis.corr(iss.spread,method='spearman').round(2))
r=smf.ols('basis~spread',iss).fit(); print('XS slope bp basis per 100bp spread:',round(r.params.spread*100,1),'t',round(r.tvalues.spread,2))
# monthly within-issuer panel
p=d.groupby(['parent_name','month']).agg(basis=('basis_bp','mean'),spread=('spread_bp','mean')).reset_index()
p=p[p.groupby('parent_name').basis.transform('size')>=6]
p['t']=p.month.astype(str)
fe=smf.ols('basis~spread+C(parent_name)',p).fit(cov_type='cluster',cov_kwds={'groups':pd.factorize(p.parent_name)[0]})
print('Within-issuer (issuer FE, monthly, clustered by issuer): slope per 100bp',round(fe.params.spread*100,1),'t',round(fe.tvalues.spread,2),'n',len(p))
fe2=smf.ols('basis~spread+C(parent_name)+C(t)',p).fit(cov_type='cluster',cov_kwds={'groups':pd.factorize(p.parent_name)[0]})
print('Issuer + month FE: slope per 100bp',round(fe2.params.spread*100,1),'t',round(fe2.tvalues.spread,2))
for nm in ['Oman, Sultanate of (Government)','Bahrain, Kingdom of (Government)','Sharjah, Emirate Of','Saudi Arabia, Kingdom of (Government)']:
    q=p[p.parent_name==nm]; print(nm[:20],'corr',round(q.basis.corr(q.spread),2),'months',len(q))
print('--- mechanical-bias checks ---')
d['spread_s']=(d.y_sukuk-d.ust)*100
p=d.groupby(['parent_name','month']).agg(basis=('basis_bp','mean'),spread=('spread_bp','mean'),spread_s=('spread_s','mean')).reset_index()
p=p[p.groupby('parent_name').basis.transform('size')>=6].sort_values(['parent_name','month'])
p['spread_lag3']=p.groupby('parent_name').spread.shift(3)
g=lambda df: pd.factorize(df.parent_name)[0]
for x in ['spread_s','spread_lag3']:
    q=p.dropna(subset=[x])
    f=smf.ols(f'basis~{x}+C(parent_name)',q).fit(cov_type='cluster',cov_kwds={'groups':g(q)})
    print(x,'issuer FE slope per 100bp',round(f.params[x]*100,1),'t',round(f.tvalues[x],2))
# cross-section using sukuk-leg spread
iss=d.groupby('parent_name').agg(basis=('basis_bp','mean'),ss=('spread_s','mean'))
print('XS corr with sukuk-leg spread', round(iss.basis.corr(iss.ss),2))
# ex Dubai (20y brackets) and ex BAPCO
for drop in [['Dubai, Emirate of'],['BAPCO Energies BSCC Closed'],['Dubai, Emirate of','DP World Ltd']]:
    q=p[~p.parent_name.isin(drop)]
    f=smf.ols('basis~spread_s+C(parent_name)',q).fit(cov_type='cluster',cov_kwds={'groups':g(q)})
    print('drop',drop,'slope(sukuk-leg spread)',round(f.params.spread_s*100,1),'t',round(f.tvalues.spread_s,2))
