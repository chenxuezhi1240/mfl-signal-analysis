"""漏磁信号位置域分析。运行: python mfl_analysis.py input.csv --out result

软件流程借鉴 Sun et al., Sensors & Actuators A 391 (2025) 116668。
默认逐通道处理；只有显式指定 --radial-channels 才执行径向差分。
"""
from pathlib import Path
import argparse
import json
import sys
import copy
import traceback
import hashlib
import shutil
from datetime import datetime

try:
    import numpy as np
    import pandas as pd
    from scipy.signal import savgol_filter, find_peaks
    from scipy.ndimage import uniform_filter1d
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mfl_enhancements import analyze_extensions
except ImportError as exc:
    raise SystemExit(f'缺少依赖: {exc}\n请执行: python -m pip install -r requirements.txt')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', nargs='?', help='CSV 或文件夹；默认扫描项目 input，成功后将原始 CSV 移入 input_pre')
    p.add_argument('--out', default=None, help='结果根目录；默认是项目下的 output')
    p.add_argument('--pos-min', type=float, default=10.0)
    p.add_argument('--pos-max', type=float, default=800.0)
    p.add_argument('--step', type=float, default=1.0, help='位置重采样步长，原始 pos 单位')
    p.add_argument('--sg-window', type=int, default=81, help='SG 窗口，奇数采样点')
    p.add_argument('--sg-order', type=int, default=1)
    p.add_argument('--mean-window', type=int, default=10)
    p.add_argument('--peak-sigma', type=float, default=6.0, help='探索性 prominence 阈值倍数')
    p.add_argument('--peak-distance', type=float, default=30.0, help='参考通道候选峰最小间距')
    p.add_argument('--feature-radius', type=float, default=25.0)
    p.add_argument('--reference', default='f13', choices=[f'f{i}' for i in range(9,16)])
    p.add_argument('--radial-channels', nargs='+', help='仅在确认同方向、不同提离高度后指定，例如 f9 f10 f11 f12；按径向顺序填写')
    p.add_argument('--compare-means', type=int, nargs='+', default=[1,3,5,10], help='均值窗口对照；1 表示不平滑')
    p.add_argument('--compare-sg-windows', type=int, nargs='+', default=[81,121], help='背景窗口对照；阶数与主流程相同')
    p.add_argument('--labels', help='真实缺口标注 CSV，必须有 defect_id,pos,tolerance；深度宽度可选')
    p.add_argument('--labels-complete', action='store_true', help='确认标注覆盖分析区所有缺陷后，才统计未匹配候选为误报')
    p.add_argument('--background-range', type=float, nargs=2, action='append', default=[], metavar=('LEFT','RIGHT'), help='用户确认的无缺陷区，可重复指定')
    p.add_argument('--channel-offsets', help='已知位置偏移 JSON；校正位置=测得位置减去偏移，单位同 pos')
    p.add_argument('--merge-distance', type=float, default=25, help='多通道候选按位置分组的最大组内跨度；不是缺陷尺寸')
    p.add_argument('--overwrite', action='store_true', help='覆盖指定 --out 目录；默认每次建立独立运行子目录')
    return p


def process_signals(values, window, order, mean_window):
    baseline = savgol_filter(values, window, order, axis=0, mode='interp')
    detrended = values - baseline
    # 偶数窗口采用 scipy uniform_filter1d(origin=0) 的居中约定，边界反射。
    smooth = uniform_filter1d(detrended, size=mean_window, axis=0, mode='reflect')
    return baseline, detrended, smooth


def process_file(args, destination):
    source = Path(args.input).resolve()
    out = Path(destination).resolve()
    if not (args.pos_min < args.pos_max and args.step > 0):
        raise ValueError('位置范围或重采样步长无效。')
    if args.sg_window < 3 or args.sg_window % 2 != 1 or not 0 <= args.sg_order < args.sg_window:
        raise ValueError('SG 窗口必须是至少 3 点的奇数，且阶数非负并小于窗口。')
    if args.mean_window < 1 or min(args.peak_sigma,args.peak_distance,args.feature_radius) <= 0:
        raise ValueError('均值窗口及候选峰参数必须为正数。')
    if args.merge_distance<=0 or any(n<1 for n in args.compare_means):
        raise ValueError('分组距离和对比均值窗口必须为正数。')
    if any(n<3 or n%2!=1 or n<=args.sg_order for n in args.compare_sg_windows):
        raise ValueError('对照 SG 窗口必须为大于阶数的奇数。')
    if args.labels_complete and not args.labels:
        raise ValueError('--labels-complete 必须同时提供 --labels。')
    cols = [f'f{i}' for i in range(9,16)]
    if args.radial_channels and (len(args.radial_channels)<2 or len(set(args.radial_channels))!=len(args.radial_channels) or any(c not in cols for c in args.radial_channels)):
        raise ValueError('--radial-channels 必须包含至少两个互不重复的 f9–f15 通道。')
    encoding='utf-8-sig'
    try:
        d = pd.read_csv(source,encoding=encoding)
    except UnicodeDecodeError:
        encoding='gb18030'
        d = pd.read_csv(source,encoding=encoding)
    required = ['ts', 'pos'] + cols
    if any(c not in d for c in required):
        raise ValueError(f'CSV 必须包含: {required}')
    numeric = d[['pos']+cols].apply(pd.to_numeric,errors='raise')
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError('输入含缺失或非有限数值；请先检查，不会自动填补原始缺测。')
    t = pd.to_datetime(d.ts,utc=True,errors='raise')
    if len(d)<3 or t.isna().any():
        raise ValueError('至少需要 3 行数据，时间戳不允许缺失。')
    elapsed = (t-t.iloc[0]).dt.total_seconds().to_numpy()
    dt = np.diff(elapsed)
    if np.any(dt <= 0):
        raise ValueError('时间戳必须严格递增，程序不会自动排序或合并重复时间。')
    pos = numeric.pos.to_numpy()
    mask = (pos > args.pos_min)&(pos < args.pos_max)
    ids = np.flatnonzero(mask)
    if len(ids) < 3:
        raise ValueError('指定位置范围内的数据不足。')
    gap_limit = max(.1,5*float(np.median(dt)))
    cuts = np.flatnonzero((np.diff(ids)>1)|(np.diff(elapsed[ids])>gap_limit))+1
    runs = np.split(ids,cuts)
    chosen = max(runs,key=len)
    p = pos[chosen]
    delta = np.diff(p)
    if not (np.all(delta>0) or np.all(delta<0)):
        raise ValueError('选定片段不是严格单向运动（可能含停留、回扫或位置抖动）。请缩小 --pos-min/--pos-max；不会把往返扫描直接混合插值。')
    reverse = bool(delta[0]<0)
    if reverse:
        chosen = chosen[::-1]
    xp = pos[chosen]
    grid = np.arange(np.ceil(xp[0]/args.step),np.floor(xp[-1]/args.step)+1)*args.step
    if len(grid) < max(args.sg_window,args.mean_window):
        raise ValueError('重采样数据长度不足以支持指定滤波窗口。')
    y = np.column_stack([np.interp(grid,xp,numeric[c].to_numpy()[chosen]) for c in cols])
    baseline, detrended, smooth = process_signals(y,args.sg_window,args.sg_order,args.mean_window)
    edge = args.sg_window//2 + int(np.ceil(args.mean_window/2))
    interior = np.arange(len(grid))
    interior = (interior>=edge)&(interior<len(grid)-edge)
    if not interior.any():
        raise ValueError('扣除滤波边界影响区后无可用于候选峰检测的数据。')

    # 读取已知元数据字段，仅作为数据，不执行其中任何文本。
    meta_dir = source.parent.parent if source.parent.name.lower()=='raw' else source.parent
    manifest_path = meta_dir/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig')) if manifest_path.exists() else {}
    unit_x = str(manifest.get('position_unit','原始位置单位'))
    unit_y = str(manifest.get('signal_unit','原始信号单位'))
    out.mkdir(parents=True,exist_ok=True)
    result = pd.DataFrame({'pos':grid,'filter_edge':(~interior).astype(int)})
    for j,c in enumerate(cols):
        for label,array in [('resampled',y),('baseline',baseline),('detrended',detrended),('processed',smooth)]:
            result[f'{c}_{label}'] = array[:,j]
    result.to_csv(out/'processed_signals.csv',index=False,encoding='utf-8-sig')

    # 候选峰只是探索性参考：处理后参考通道的正峰，不是已校准的缺陷判定器。
    j = cols.index(args.reference)
    z = smooth[:,j]
    center = np.median(z[interior])
    scale = 1.4826*np.median(np.abs(z[interior]-center))
    prominence = max(args.peak_sigma*scale,np.finfo(float).eps)
    peaks, properties = find_peaks(z,height=center+prominence,prominence=prominence,distance=max(1,int(np.ceil(args.peak_distance/args.step))))
    valid = interior[peaks] & (z[peaks]>center)
    peaks = peaks[valid]
    prominences = properties['prominences'][valid]
    candidates = pd.DataFrame({'candidate_id':np.arange(1,len(peaks)+1),'reference_channel':args.reference,
                               'reference_pos':grid[peaks],'processed_peak':z[peaks],'prominence':prominences})
    candidates.to_csv(out/'candidate_peaks.csv',index=False,encoding='utf-8-sig')
    features=[]
    for k,idx in enumerate(peaks,1):
        local=np.flatnonzero(np.abs(grid-grid[idx])<=args.feature_radius)
        for j,c in enumerate(cols):
            imin=local[np.argmin(smooth[local,j])]; imax=local[np.argmax(smooth[local,j])]
            features.append({'candidate_id':k,'reference_pos':grid[idx],'channel':c,
                'window_left':grid[local[0]],'window_right':grid[local[-1]],
                'positive_peak':smooth[imax,j],'positive_peak_pos':grid[imax],
                'negative_peak':smooth[imin,j],'negative_peak_pos':grid[imin],
                'peak_to_peak':smooth[imax,j]-smooth[imin,j],
                'peak_valley_spacing':abs(grid[imax]-grid[imin]),
                'rms':float(np.sqrt(np.mean(smooth[local,j]**2))),
                'energy_integral':float(np.trapezoid(smooth[local,j]**2,grid[local])),
                'raw_local_peak_to_peak':float(np.ptp(y[local,j]))})
    fields=['candidate_id','reference_pos','channel','window_left','window_right','positive_peak','positive_peak_pos','negative_peak','negative_peak_pos','peak_to_peak','peak_valley_spacing','rms','energy_integral','raw_local_peak_to_peak']
    pd.DataFrame(features,columns=fields).to_csv(out/'candidate_features.csv',index=False,encoding='utf-8-sig')

    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False,'font.size':10})
    fig,axs=plt.subplots(7,2,figsize=(15,20),sharex=True,layout='constrained')
    for j,c in enumerate(cols):
        a,b=axs[j]
        a.plot(grid,y[:,j],lw=1,label='重采样信号');a.plot(grid,baseline[:,j],lw=1,label='SG 背景')
        b.plot(grid,detrended[:,j],lw=.7,alpha=.45,label='去背景');b.plot(grid,smooth[:,j],lw=1,label='均值滤波后')
        for ax in (a,b):
            ax.set_title(c);ax.set_ylabel(unit_y);ax.grid(alpha=.2)
            ax.axvspan(grid[0],grid[edge],color='gray',alpha=.1)
            ax.axvspan(grid[-edge-1],grid[-1],color='gray',alpha=.1)
            ax.legend(loc='best',fontsize=8)
        for idx in peaks:b.axvline(grid[idx],color='tomato',lw=.7,ls='--',alpha=.6)
    for ax in axs[-1]:ax.set_xlabel(f'位置 / {unit_x}')
    fig.suptitle('f9–f15 处理前后对比\n灰区为滤波边界影响区；红线是参考通道的候选峰，不是确认缺陷',fontsize=15)
    fig.savefig(out/'processing_comparison.png',dpi=130);plt.close(fig)
    fig,ax=plt.subplots(figsize=(13,5),layout='constrained')
    ax.plot(grid,z,label=f'{args.reference} 处理后',lw=1.3)
    for k,idx in enumerate(peaks,1):
        ax.plot(grid[idx],z[idx],'o',color='tomato');ax.annotate(f'C{k}: {grid[idx]:.1f}',(grid[idx],z[idx]),xytext=(6,8),textcoords='offset points')
    ax.margins(y=.18)
    ax.set(xlabel=f'位置 / {unit_x}',ylabel=unit_y,title=f'参考通道候选峰（峰突出度及相对中位数高度阈值 {prominence:.4g} {unit_y}）')
    ax.grid(alpha=.2);ax.legend();fig.savefig(out/'reference_candidates.png',dpi=150);plt.close(fig)

    radial_note='未执行径向差分；默认逐通道处理。'
    if args.radial_channels:
        radial=args.radial_channels
        if len(radial)<2 or len(set(radial))!=len(radial) or any(c not in cols for c in radial):
            raise ValueError('--radial-channels 必须包含至少两个互不重复的 f9–f15 通道。')
        diffs=np.diff(y[:,[cols.index(c) for c in radial]],axis=1)
        rb,rd,rs=process_signals(diffs,args.sg_window,args.sg_order,args.mean_window)
        rdf=pd.DataFrame({'pos':grid,'filter_edge':(~interior).astype(int)})
        for k in range(len(radial)-1):
            label=f'{radial[k+1]}_minus_{radial[k]}'
            rdf[label+'_raw']=diffs[:,k];rdf[label+'_processed']=rs[:,k]
        rdf['combined']=rs.sum(axis=1)
        rdf.to_csv(out/'radial_difference.csv',index=False,encoding='utf-8-sig')
        # 同样线性处理下验证相邻差分叠加与两端差分的一致性。
        endpoint=process_signals((y[:,cols.index(radial[-1])]-y[:,cols.index(radial[0])])[:,None],args.sg_window,args.sg_order,args.mean_window)[2][:,0]
        if not np.allclose(endpoint,rs.sum(axis=1),atol=1e-9,rtol=1e-9):
            raise AssertionError('径向差分叠加一致性验证失败。')
        radial_note='已按用户显式指定顺序执行径向差分: '+', '.join(radial)+'。物理配对必须由实验布置确认。'

    stats={
        'source':str(source),'parameters':vars(args),'units':{'position':unit_x,'signal':unit_y},
        'input_encoding':encoding,'input_rows':len(d),'input_duration_s':float(elapsed[-1]),
        'selected_rows':len(chosen),'selected_original_rows_1based_including_header':[int(chosen.min()+2),int(chosen.max()+2)],
        'selected_time_s':[float(elapsed[chosen].min()),float(elapsed[chosen].max())],
        'selected_pos_range':[float(xp[0]),float(xp[-1])],'scan_direction':'decreasing' if reverse else 'increasing',
        'position_runs_found':len(runs),'resampled_rows':len(grid),
        'original_spacing_min_median_max':list(map(float,[np.diff(xp).min(),np.median(np.diff(xp)),np.diff(xp).max()])),
        'sg_window_endpoint_span':(args.sg_window-1)*args.step,
        'mean_window_endpoint_span':(args.mean_window-1)*args.step,
        'excluded_edge_points_each_side':edge,'reference_robust_scale':float(scale),
        'prominence_threshold':float(prominence),'candidates':candidates.to_dict(orient='records'),
        'height_threshold':float(center+prominence),
        'radial_processing':radial_note,
        'limitations':['候选峰使用参考通道正峰及探索性 MAD 阈值，可能漏检负峰、弱缺陷或其他通道独有缺陷。',
          'MAD 尺度来自本次整段内部处理信号，并非独立无缺陷噪声标定；不等于检出置信度或论文 ROC 阈值。',
          '过滤边界不参与候选峰搜索；候选窗口不是实物缺陷边界。',
          '论文滤波参数仅作起点，必须检查峰值压低、基线失真和缺陷宽度影响。',
          '每次运行会覆盖结果目录中同名结果文件；原始输入不修改。']}
    (out/'analysis_summary.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 本次信号处理结果','',f'- 输入采样点：{len(d)}；选定运动片段：{len(chosen)} 点。',
           f'- 重采样：{grid[0]:g}–{grid[-1]:g} {unit_x}，间隔 {args.step:g}，共 {len(grid)} 点。',
           f'- SG：{args.sg_window} 点，{args.sg_order} 阶；均值窗口：{args.mean_window} 点。',
           f'- {args.reference} 参考候选峰：'+('、'.join(f'{v:.1f} {unit_x}' for v in grid[peaks]) or '无'),
           '- '+radial_note,'','候选峰只是需要人工核对的局部异常，未依据实物位置标定，不能据此确定缺陷数量、尺寸或深度。',
           '这里只对明确选定片段插值，未修复或重标定原始信号；请核对该片段是否覆盖全部实物缺陷。','',
           '## 输出文件','- processed_signals.csv：位置、边界标记及各通道重采样/背景/去背景/最终信号。',
           '- candidate_peaks.csv：参考通道候选峰。','- candidate_features.csv：每个候选窗口内各通道的峰、谷、峰峰值等。',
           '- processing_comparison.png：所有通道处理前后对比。','- reference_candidates.png：参考通道候选峰图。',
           '- analysis_summary.json：实际参数、所选原始行号、阈值和限制。']
    (out/'结果说明.md').write_text('\n'.join(lines),encoding='utf-8')
    extension = analyze_extensions(args,grid,y,cols,unit_x,unit_y,out,process_signals)
    stats['enhancements']=extension
    stats['actual_output_directory']=str(out)
    stats['limitations'][-1]='默认每次创建新运行目录；只有显式 --overwrite 才覆盖指定目录。'
    (out/'analysis_summary.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'结果说明.md').open('a',encoding='utf-8') as f:
        f.write('\n\n## 优化分析\n'+extension['report'])
    return {'output':str(out),'rows':len(grid),'candidates':stats['candidates']}


def file_digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def archive_input(source, inbox, archive, expected_digest):
    """校验路径和内容后归档；同名文件独立保存，不覆盖已有实验数据。"""
    source = source.resolve()
    inbox, archive = inbox.resolve(), archive.resolve()
    if source.parent != inbox or archive == inbox or archive.parent != inbox.parent:
        raise ValueError('归档路径必须是项目 input 中的文件及同级 input_pre。')
    if file_digest(source) != expected_digest:
        raise ValueError('处理期间原始文件发生变化，保留在 input，请检查后重试。')
    archive.mkdir(parents=True, exist_ok=True)
    target = archive / source.name
    index = 0
    while True:
        try:
            stream = target.open('xb')
            break
        except FileExistsError:
            index += 1
            target = archive / f'{source.stem}_{index}{source.suffix}'
    try:
        with stream, source.open('rb') as original:
            shutil.copyfileobj(original, stream)
        if file_digest(target) != expected_digest or file_digest(source) != expected_digest:
            raise ValueError('归档内容校验失败，原文件保留在 input。')
        # 仅删除已校验、位于 input 内的这一份源文件，不进行递归操作。
        source.unlink()
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def main():
    args=parser().parse_args()
    project=Path(__file__).resolve().parent
    inbox=project/'input'
    archive=project/'input_pre'
    for directory in (inbox, archive, project/'output'):
        directory.mkdir(parents=True,exist_ok=True)
    target=Path(args.input).resolve() if args.input else inbox
    if not target.exists():
        raise FileNotFoundError(f'输入路径不存在: {target}')
    batch=target.is_dir()
    folder=target if batch else target.parent
    root=Path(args.out).resolve() if args.out else project/'output'
    if root in (inbox.resolve(), archive.resolve()):
        raise ValueError('结果根目录不能是 input 或 input_pre。')
    # 只扫描顶层：不会递归读取 output 或旧结果文件夹。
    sources=sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower()=='.csv'),key=lambda p:p.name.lower()) if batch else [target]
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    root.mkdir(parents=True,exist_ok=True)
    required={'ts','pos'}|{f'f{i}' for i in range(9,16)}
    records=[]
    def save_summary():
        pd.DataFrame(records,columns=['input_file','status','output_directory','resampled_rows','archived_file','source_sha256','message']).to_csv(root/f'batch_summary_{stamp}.csv',index=False,encoding='utf-8-sig')
    for index,source in enumerate(sources,1):
        destination=root/source.stem
        if not args.overwrite:destination=destination/f'run_{stamp}'
        try:
            # 标注表、已处理 CSV 等缺少原始通道结构的文件不参与处理。
            try:header=pd.read_csv(source,nrows=0,encoding='utf-8-sig')
            except UnicodeDecodeError:header=pd.read_csv(source,nrows=0,encoding='gb18030')
            missing=required-set(header.columns)
            if missing:
                status='skipped' if batch else 'failed'
                records.append({'input_file':str(source),'status':status,'output_directory':'','resampled_rows':None,'message':'缺少原始信号列: '+','.join(sorted(missing))})
                print(f'[{index}/{len(sources)}] {status}: {source.name}',flush=True)
                save_summary();continue
            # 输出文件不能覆盖源文件，即使用户显式指定了特殊 --out。
            if source.parent==destination:
                raise ValueError('结果目录不能与当前输入文件所在目录相同。')
            print(f'[{index}/{len(sources)}] 正在处理: {source.name}',flush=True)
            managed=source.resolve().parent==inbox.resolve()
            original_digest=file_digest(source) if managed else ''
            child=copy.deepcopy(args);child.input=str(source)
            result=process_file(child,destination)
            if (destination/'FAILED.txt').exists():
                (destination/'FAILED.txt').unlink()
            record={'input_file':str(source),'status':'success','output_directory':str(destination),'resampled_rows':result['rows'],'archived_file':'','source_sha256':original_digest,'message':f"参考通道候选峰 {len(result['candidates'])} 个；详见结果"}
            if managed:
                try:
                    archived=archive_input(source,inbox,archive,original_digest)
                    record['archived_file']=str(archived)
                    print(f'原始文件已归档: {archived}',flush=True)
                except Exception as exc:
                    record['status']='archive_failed'
                    record['message']=f'信号处理完成，但归档失败；原文件保留在 input: {exc}'
                    print(record['message'],flush=True)
            records.append(record)
            print(f'完成: {destination}',flush=True)
        except Exception as exc:
            # 单份输入失败不阻断批次；日志注明可能有尚未完成的中间输出。
            destination.mkdir(parents=True,exist_ok=True)
            (destination/'FAILED.txt').write_text('本文件处理失败；此目录若有图表或 CSV，均不应作为完整结果使用。\n'+traceback.format_exc(),encoding='utf-8')
            records.append({'input_file':str(source),'status':'failed','output_directory':str(destination),'resampled_rows':None,'message':str(exc)})
            print(f'失败: {source.name}: {exc}',flush=True)
        finally:
            plt.close('all')
        save_summary()
    save_summary()
    counts={s:sum(r['status']==s for r in records) for s in ['success','failed','skipped','archive_failed']}
    print(f"批次结束：成功 {counts['success']}，处理失败 {counts['failed']}，跳过 {counts['skipped']}，归档失败 {counts['archive_failed']}。结果: {root}",flush=True)
    if not sources:print(f'没有待处理 CSV，请将原始信号 CSV 放入 {inbox} 后再次运行。')
    if counts['failed'] or counts['archive_failed']:raise SystemExit(1)


if __name__=='__main__':
    try:
        main()
    except (ValueError,FileNotFoundError) as exc:
        raise SystemExit(f'处理失败: {exc}')
