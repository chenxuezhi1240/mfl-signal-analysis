"""多通道候选、参数敏感性与实物标注评价。与 mfl_analysis.py 放在一起。"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from scipy.optimize import linear_sum_assignment


def read_csv(path):
    try:
        return pd.read_csv(path,encoding='utf-8-sig')
    except UnicodeDecodeError:
        return pd.read_csv(path,encoding='gb18030')


def detect_signed(grid,values,cols,valid,sigma,distance,step,offsets):
    rows=[];thresholds={}
    for j,c in enumerate(cols):
        z=values[:,j];center=float(np.median(z[valid]))
        scale=float(1.4826*np.median(abs(z[valid]-center)))
        threshold=max(sigma*scale,1e-12*max(1,float(np.max(abs(z)))))
        thresholds[c]={'median':center,'mad_scale':scale,'threshold':threshold}
        for sign in [1,-1]:
            idx,props=find_peaks(sign*(z-center),height=threshold,prominence=threshold,distance=max(1,int(np.ceil(distance/step))))
            for k,i in enumerate(idx):
                if valid[i]:
                    rows.append({'channel':c,'polarity':'positive' if sign==1 else 'negative',
                        'measured_pos':float(grid[i]),'corrected_pos':float(grid[i]-offsets.get(c,0)),
                        'amplitude':float(z[i]),'prominence':float(props['prominences'][k]),'threshold':threshold})
    columns=['channel','polarity','measured_pos','corrected_pos','amplitude','prominence','threshold']
    return pd.DataFrame(rows,columns=columns),thresholds


def group_events(events,distance):
    """最大组内跨度约束；不使用能跨多个缺陷无限延伸的链式聚类。"""
    e=events.sort_values('corrected_pos').copy(); e['group_id']=pd.Series(dtype=int)
    groups=[];group=[]
    def commit(members):
        part=e.loc[members];gid=len(groups)+1
        e.loc[members,'group_id']=gid
        # 每个通道先求中心，再跨通道求中位数，避免双极通道被重复加权。
        center=float(part.groupby('channel').corrected_pos.median().median())
        groups.append({'group_id':gid,'group_center':center,'left':float(part.corrected_pos.min()),
          'right':float(part.corrected_pos.max()),'support_count':int(part.channel.nunique()),
          'channels':','.join(sorted(part.channel.unique())), 'extrema_count':len(part)})
    for idx in e.index:
        if group and e.loc[idx,'corrected_pos']-e.loc[group[0],'corrected_pos']>distance:
            commit(group);group=[]
        group.append(idx)
    if group:commit(group)
    return e,pd.DataFrame(groups,columns=['group_id','group_center','left','right','support_count','channels','extrema_count'])


def evaluate_labels(labels,groups,low,high,complete):
    required=['defect_id','pos','tolerance']
    if any(c not in labels for c in required):raise ValueError('标注需要 defect_id,pos,tolerance 三列。')
    labels=labels.copy()
    if labels.empty or labels.defect_id.isna().any() or labels.defect_id.duplicated().any():
        raise ValueError('标注不能为空，defect_id 不能为空或重复。')
    for c in ['pos','tolerance']:labels[c]=pd.to_numeric(labels[c],errors='raise')
    if not np.isfinite(labels[['pos','tolerance']]).all().all() or (labels.tolerance<=0).any():
        raise ValueError('标注位置必须有限，允许误差 tolerance 必须大于零；请填写模板中的空白项。')
    excluded_groups=int(((groups.group_center<low)|(groups.group_center>high)).sum())
    groups=groups[(groups.group_center>=low)&(groups.group_center<=high)].reset_index(drop=True)
    rows=[];active=[]
    for i,r in labels.iterrows():
        # 要求整个容差窗口位于所有通道共同可评价的内部区域。
        if r.pos-r.tolerance<low or r.pos+r.tolerance>high:
            rows.append({'defect_id':r.defect_id,'actual_pos':r.pos,'status':'outside_evaluable_range','matched_group':None,'error':None})
        else:active.append(i)
    matched=set()
    if active:
        a=labels.loc[active];n=len(a);m=len(groups)
        error=np.abs(a.pos.to_numpy()[:,None]-groups.group_center.to_numpy()[None,:])
        allowed=error<=a.tolerance.to_numpy()[:,None]
        # 虚拟列允许未匹配；优先最大化一对一匹配数，再最小化归一化距离。
        penalty=n+1
        cost=np.full((n,m+n),float(penalty))
        if m:cost[:,:m]=np.where(allowed,error/a.tolerance.to_numpy()[:,None],penalty*3)
        ri,ci=linear_sum_assignment(cost)
        for r,c in zip(ri,ci):
            truth=a.iloc[r];hit=c<m and allowed[r,c]
            if hit:matched.add(int(c))
            rows.append({'defect_id':truth.defect_id,'actual_pos':float(truth.pos),'status':'matched' if hit else 'missed',
                'matched_group':int(groups.iloc[c].group_id) if hit else None,
                'error':float(groups.iloc[c].group_center-truth.pos) if hit else None})
    n=len(active);tp=len(matched)
    metrics={'evaluable_defects':n,'excluded_groups_outside_range':excluded_groups,'matched':tp,'missed':n-tp,'recall':tp/n if n else None,
        'unmatched_groups':len(groups)-tp,'false_positive_groups':len(groups)-tp if complete else None,
        'precision':tp/len(groups) if complete and len(groups) else None,
        'fpr':None,'note':'只有完整标注时才将未匹配组计为误报；没有无缺陷样本总数，故不计算 FPR、准确率或 ROC。分组中心不是经标定的物理缺陷中心。'}
    return pd.DataFrame(rows),metrics


def analyze_extensions(args,grid,y,cols,ux,uy,out,process):
    offsets={}
    if args.channel_offsets:
        offsets=json.loads(Path(args.channel_offsets).read_text(encoding='utf-8-sig'))
        if not isinstance(offsets,dict) or any(c not in cols for c in offsets):raise ValueError('位置偏移 JSON 必须是所选通道到数值的映射。')
        offsets={c:float(v) for c,v in offsets.items()}
        if not all(np.isfinite(list(offsets.values()))):raise ValueError('位置偏移必须为有限数值。')
    sg_windows=sorted(set(args.compare_sg_windows+[args.sg_window]))
    means=sorted(set(args.compare_means+[args.mean_window,1]))
    skipped=[w for w in sg_windows if w>len(grid)]
    sg_windows=[w for w in sg_windows if w<=len(grid)]
    edge=max(sg_windows)//2+int(np.ceil(max(means)/2))
    if 2*edge>=len(grid):raise ValueError('参数对照的共同内部区域不足，请缩小窗口。')
    valid=(np.arange(len(grid))>=edge)&(np.arange(len(grid))<len(grid)-edge)
    background=np.zeros(len(grid),bool)
    for a,b in args.background_range:
        if not np.isfinite([a,b]).all() or a>=b:raise ValueError('背景区必须是有限递增范围。')
        background|=(grid>=a)&(grid<=b)
    background&=valid
    if args.background_range and background.sum()<3:raise ValueError('有效内部区域中的背景采样点不足 3 个。')
    _,detrended,smooth=process(y,args.sg_window,args.sg_order,args.mean_window)
    events,thresholds=detect_signed(grid,smooth,cols,valid,args.peak_sigma,args.peak_distance,args.step,offsets)
    events,groups=group_events(events,args.merge_distance)
    events.to_csv(out/'all_channel_extrema.csv',index=False,encoding='utf-8-sig')
    groups.to_csv(out/'multichannel_groups.csv',index=False,encoding='utf-8-sig')
    windows=[(f'G{int(r.group_id)}',float(r.group_center)) for _,r in groups.iterrows()]
    label_metrics=None;labels=None
    common_low=max(grid[edge]-offsets.get(c,0) for c in cols)
    common_high=min(grid[-edge-1]-offsets.get(c,0) for c in cols)
    if args.labels:
        labels=read_csv(args.labels)
        matches,label_metrics=evaluate_labels(labels,groups,common_low,common_high,args.labels_complete)
        matches.to_csv(out/'label_matches.csv',index=False,encoding='utf-8-sig')
        (out/'label_metrics.json').write_text(json.dumps(label_metrics,ensure_ascii=False,indent=2),encoding='utf-8')
        windows=[(f'T:{r.defect_id}',float(r.pos)) for _,r in labels.iterrows() if common_low<=r.pos<=common_high]
    comparison=[];noise=[];variants={}
    for w in sg_windows:
        b,det,_=process(y,w,args.sg_order,1)
        for mean in means:
            _,_,s=process(y,w,args.sg_order,mean)
            variants[(w,mean)]=s
            for j,c in enumerate(cols):
                if background.sum()>=3:
                    before=float(np.std(det[background,j],ddof=1));after=float(np.std(s[background,j],ddof=1))
                    noise.append({'channel':c,'sg_window':w,'mean_window':mean,'background_samples':int(background.sum()),'std_before':before,'std_after':after,'std_ratio':after/before if before>1e-12 else None})
                for label,center in windows:
                    measured_center=center+offsets.get(c,0)
                    ids=np.flatnonzero((abs(grid-measured_center)<=args.feature_radius)&valid)
                    if len(ids)<3:continue
                    # 同一 SG 背景、同一窗口，比较降噪引起的变化；使用固定极性防止峰谷互换。
                    anchor=ids[np.argmax(abs(det[ids,j]))];sign=1 if det[anchor,j]>=0 else -1
                    peak=ids[np.argmax(sign*s[ids,j])]
                    before=float(abs(det[anchor,j]));after=float(sign*s[peak,j])
                    comparison.append({'window_id':label,'center':center,'channel':c,'sg_window':w,'mean_window':mean,
                        'polarity':'positive' if sign>0 else 'negative','detrended_peak_abs':before,'smoothed_same_polarity_peak':after,
                        'retention_percent':100*after/before if before>1e-12 else None,
                        'peak_shift':float(grid[peak]-grid[anchor]),'window_touches_edge':bool(measured_center-args.feature_radius<grid[edge] or measured_center+args.feature_radius>grid[-edge-1]),
                        'detrended_peak_pos':float(grid[anchor]),'smoothed_peak_pos':float(grid[peak])})
    pd.DataFrame(comparison,columns=['window_id','center','channel','sg_window','mean_window','polarity','detrended_peak_abs','smoothed_same_polarity_peak','retention_percent','peak_shift','window_touches_edge','detrended_peak_pos','smoothed_peak_pos']).to_csv(out/'parameter_comparison.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(noise,columns=['channel','sg_window','mean_window','background_samples','std_before','std_after','std_ratio']).to_csv(out/'background_comparison.csv',index=False,encoding='utf-8-sig')
    fig,axs=plt.subplots(len(sg_windows),1,figsize=(13,4*len(sg_windows)),sharex=True,squeeze=False,layout='constrained')
    for ax,w in zip(axs[:,0],sg_windows):
        for mean in means:ax.plot(grid,variants[w,mean][:,cols.index(args.reference)],label=f'均值 {mean} 点'+('（不平滑）' if mean==1 else ''),lw=1)
        ax.set_title(f'{args.reference}：SG {w} 点 / {args.sg_order} 阶');ax.set_ylabel(uy);ax.grid(alpha=.2);ax.legend(ncol=3)
    axs[-1,0].set_xlabel(f'位置 / {ux}');fig.savefig(out/'parameter_comparison.png',dpi=140);plt.close(fig)
    fig,ax=plt.subplots(figsize=(13,6),layout='constrained')
    for j,c in enumerate(cols):
        subset=events[events.channel==c]
        for polarity,marker in [('positive','^'),('negative','v')]:
            part=subset[subset.polarity==polarity]
            ax.scatter(part.corrected_pos,np.full(len(part),j),marker=marker,s=35,color='tab:blue' if polarity=='positive' else 'tab:orange')
    for _,r in groups.iterrows():ax.axvspan(r.left-.5,r.right+.5,color='gray',alpha=.1)
    if labels is not None:
        for _,r in labels.iterrows():ax.axvline(r.pos,color='green',ls='--',lw=1)
    ax.set_yticks(range(len(cols)),cols);ax.set_xlabel(f'校正位置 / {ux}' if offsets else f'测得位置 / {ux}')
    ax.set_xlim(min(grid[0]-offsets.get(c,0) for c in cols),max(grid[-1]-offsets.get(c,0) for c in cols))
    ax.set_title('多通道候选极值：蓝色正峰 / 橙色负谷\n灰区为位置邻近分组，不代表独立缺陷；绿色线为用户标注')
    ax.grid(alpha=.2);fig.savefig(out/'multichannel_candidates.png',dpi=140);plt.close(fig)
    report=(f'- 多通道检出 {len(events)} 个候选极值，按最大跨度 {args.merge_distance:g} {ux} 分为 {len(groups)} 组。组数不是缺陷数，正负两瓣可能分组，邻近缺陷也可能合组。\n'
       f'- 参数对照：SG {sg_windows}，均值 {means}。1 点表示不做均值平滑。\n'
       '- parameter_comparison.csv 逐窗口记录同一基线下峰值保留率和位移；parameter_comparison.png 可视化各参数。\n'
       '- '+('已使用用户指定无缺陷区计算背景标准差。' if background.any() else '未提供确认的无缺陷区，因此背景降噪评价留空，未把未知区域自动当成无缺陷。')+'\n'
       '- '+('已读取用户通道偏移。' if offsets else '未提供通道偏移，分组按测得坐标进行，仅供人工核对。')+'\n'
       '- '+('已生成标注匹配表；评价未使用自动调参。' if labels is not None else '未提供实物标注，不计算检出率、误报率或最佳参数。')+'\n'
       '- 所有 MAD 阈值都是探索性阈值，不是置信度。比较多个参数不会自动证明哪个参数最好。')
    return {'version':'2.0','thresholds':thresholds,'extrema_count':len(events),'group_count':len(groups),
      'offsets':offsets,'common_edge_points':edge,'skipped_sg_windows':skipped,'label_metrics':label_metrics,'report':report}
