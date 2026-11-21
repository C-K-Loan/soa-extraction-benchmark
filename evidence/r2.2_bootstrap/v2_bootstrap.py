"""Claim 2: cluster bootstrap over schedule groups. Own implementation, numpy, seed 20261118, B=10000."""
import csv, numpy as np, itertools
import os
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','results','')
SYS=['medical_llm_medium_schema_constrained','gpt_56_terra','gemini_38_flash','claude_sonnet_55']
NM={SYS[0]:'MedLLM-Medium',SYS[1]:'GPT',SYS[2]:'Gemini',SYS[3]:'Claude'}
rows=list(csv.DictReader(open(R+'accuracy_per_group.csv')))
gids=sorted({r['group_id'] for r in rows}); gi={g:i for i,g in enumerate(gids)}
# counts[sys][comp] -> (G,3) array tp,fp,fn
CMP=['act','con','ref','cell','att']
cnt={s:{c:np.zeros((len(gids),3)) for c in CMP} for s in SYS}
for r in rows:
    if r['system'] in cnt:
        for c in ('act','con','ref','cell'):
            cnt[r['system']][c][gi[r['group_id']]]=[int(r[f'{c}_{k}']) for k in('tp','fp','fn')]
for r in csv.DictReader(open(R+'attachment_per_group.csv')):
    if r['system'] in cnt:
        cnt[r['system']]['att'][gi[r['group_id']]]+= [int(r[k]) for k in('tp','fp','fn')]
def tot(s,comps): return sum(cnt[s][c] for c in comps)   # (G,3)
def f1(a): d=2*a[...,0]+a[...,1]+a[...,2]; return np.where(d>0,2*a[...,0]/np.maximum(d,1),0)
ALL=CMP
# sanity vs published micro csv
pub={r['system']:r for r in csv.DictReader(open(R+'accuracy_micro_t060.csv'))}
for s in SYS: print('check',NM[s],'pooled SoA5 %.4f published %s'%(f1(tot(s,ALL).sum(0)),pub[s]['soa5']),'cellF1 %.4f pub %s'%(f1(tot(s,['cell']).sum(0)),pub[s]['cell_f1']))
B=10000; rng=np.random.default_rng(20261118); G=len(gids)
idx=rng.integers(0,G,size=(B,G))
def boot(s,comps):
    t=tot(s,comps); return f1(t[idx].sum(1))
def ci(v): return np.percentile(v,[2.5,97.5])
res={}
for s in SYS:
    for nm,comps in(('SoA',ALL),('cellF1',['cell'])):
        res[s,nm]=boot(s,comps); lo,hi=ci(res[s,nm])
        print(f'{NM[s]:14s} {nm:6s} point {f1(tot(s,comps).sum(0)):.3f} CI [{lo:.3f},{hi:.3f}]')
M=np.stack([res[s,'SoA'] for s in SYS],1)
best=M.max(1,keepdims=True); share=((M==best)/ (M==best).sum(1,keepdims=True)).mean(0)
print('first-place share (ties split):',{NM[s]:round(float(x),3) for s,x in zip(SYS,share)})
print('\npaired SoA differences (resample groups, both systems same resample):')
for a,b in itertools.combinations(SYS,2):
    d=res[a,'SoA']-res[b,'SoA']; lo,hi=ci(d)
    print(f'  {NM[a]:14s} - {NM[b]:14s} point {f1(tot(a,ALL).sum(0))-f1(tot(b,ALL).sum(0)):+.3f} mean {d.mean():+.3f} CI [{lo:+.3f},{hi:+.3f}] P(a>b)={np.mean(d>0):.3f}')
for a,b in [(SYS[0],SYS[3]),(SYS[1],SYS[2])]:
    d=res[a,'cellF1']-res[b,'cellF1']; lo,hi=ci(d)
    print(f'  cellF1 {NM[a]:14s} - {NM[b]:14s} CI [{lo:+.3f},{hi:+.3f}] P(a>b)={np.mean(d>0):.3f}')
# cell recall highest
def rec(s): t=tot(s,['cell'])[idx].sum(1); return t[:,0]/(t[:,0]+t[:,2])
r=np.stack([rec(s) for s in SYS],1); print('P(MedLLM highest cell recall)=',np.mean(r.argmax(1)==0))
print('\nleave-one-group-out pooled SoA:')
for g in gids:
    keep=[i for i in range(G) if gids[i]!=g]
    sc=sorted(((f1(tot(s,ALL)[keep].sum(0)),NM[s]) for s in SYS),reverse=True)
    print(' drop',g.split('__')[0]+g[-5:],' > '.join(f'{n} {v:.3f}' for v,n in sc))
# sensitivity: cluster by protocol (5 clusters: g001/g002 of NCT01667081 merged)
prot=sorted({g.split('__')[0] for g in gids}); pidx=rng.integers(0,len(prot),size=(B,len(prot)))
mem=[[i for i,g in enumerate(gids) if g.startswith(p)] for p in prot]
print('\nsensitivity: resample 5 protocols')
def pb(s): 
    t=tot(s,ALL); pt=np.stack([t[m].sum(0) for m in mem]); return f1(pt[pidx].sum(1))
P={s:pb(s) for s in SYS}
for s in SYS: print(f'  {NM[s]:14s} CI',np.round(ci(P[s]),3))
for a,b in [(SYS[2],SYS[1]),(SYS[1],SYS[0]),(SYS[2],SYS[0]),(SYS[3],SYS[0]),(SYS[2],SYS[3])]:
    d=P[a]-P[b]; print(f'  {NM[a]}-{NM[b]} CI',np.round(ci(d),3),'P>0 %.3f'%np.mean(d>0))
