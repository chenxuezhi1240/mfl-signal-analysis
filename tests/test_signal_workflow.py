import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from mfl_enhancements import detect_signed,group_events,evaluate_labels
from mfl_analysis import process_signals

grid=np.arange(501.)
x=5*np.exp(-.5*((grid-150)/5)**2)-4*np.exp(-.5*((grid-350)/5)**2)
y=np.column_stack([x,np.interp(grid-7,grid,x)])
_,_,s=process_signals(y,81,1,5)
valid=(grid>60)&(grid<440)
events,_=detect_signed(grid,s,['a','b'],valid,6,30,1,{'b':7})
assert any((events.polarity=='positive')&(abs(events.corrected_pos-150)<2))
assert any((events.polarity=='negative')&(abs(events.corrected_pos-350)<2))
# 单个数据源重复正负极值不增加支持通道数；避免链式过度合并。
e=pd.DataFrame({'channel':['a','a','b','b'],'corrected_pos':[10.,15.,30.,50.]})
_,groups=group_events(e,25)
assert len(groups)==2 and groups.iloc[0].support_count==2
# 一对一标注匹配：两个标注不能同时匹配同一个候选。
g=pd.DataFrame({'group_id':[1,2],'group_center':[100.,300.]})
truth=pd.DataFrame({'defect_id':['one','two','edge'],'pos':[99.,101.,10.],'tolerance':[5.,5.,20.]})
matches,metrics=evaluate_labels(truth,g,20,400,False)
assert metrics['matched']==1 and metrics['missed']==1 and metrics['false_positive_groups'] is None
assert 'outside_evaluable_range' in matches.status.to_list()
_,metrics=evaluate_labels(truth,g,20,400,True)
assert metrics['false_positive_groups']==1 and metrics['precision']==.5
empty=g.iloc[:0]
_,metrics=evaluate_labels(truth,empty,20,400,True)
assert metrics['matched']==0 and metrics['missed']==2 and metrics['precision'] is None
const=np.ones((len(grid),2))*10
_,_,flat=process_signals(const,81,1,5)
events,_=detect_signed(grid,flat,['a','b'],valid,6,30,1,{})
assert events.empty
print('PASS: signed detection, known offsets, bounded grouping, one-to-one truth matching, boundary exclusion, empty candidates, constant signal')

