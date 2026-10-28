"""Predeclared cycle analysis; no simulated data generation and no approval changes."""
import statistics,math

def analyze(rows,plan):
 if len(rows)<2:raise ValueError('INSUFFICIENT_DATA')
 if any(abs((b['time_s']-a['time_s'])-.02)>1e-6 for a,b in zip(rows,rows[1:])):raise ValueError('NOT_0_02S_GRID')
 timing={'StartOfInhale','StartOfExhale','StartOfCardiacCycle'};starts=[];previous=False
 for i,row in enumerate(rows):
  for key in ['left_pleural_pressure_cmH2O','left_pleural_volume_mL']:
   if not isinstance(row.get(key),(int,float)) or not math.isfinite(row[key]):raise ValueError('MISSING_NONFINITE')
  if row['left_pleural_volume_mL']<0:raise ValueError('NEGATIVE_GAS_VOLUME')
  active=set(row['active_events'])
  if active-timing:raise ValueError('PATHOLOGICAL_OR_STABILIZING_EVENT')
  onset='StartOfInhale' in active
  if onset and not previous:starts.append(i)
  previous=onset
 if len(starts)<11:raise ValueError('FEWER_THAN_10_COMPLETE_CYCLES')
 cycles=[]
 for a,b in zip(starts[-11:],starts[-10:]):
  selected=rows[a:b];cycles.append({'start_s':rows[a]['time_s'],'end_s':rows[b]['time_s'],'period_s':rows[b]['time_s']-rows[a]['time_s'],'pressure_mean':statistics.mean(x['left_pleural_pressure_cmH2O'] for x in selected),'volume_mean':statistics.mean(x['left_pleural_volume_mL'] for x in selected),'pressure_range':[min(x['left_pleural_pressure_cmH2O'] for x in selected),max(x['left_pleural_pressure_cmH2O'] for x in selected)],'volume_range':[min(x['left_pleural_volume_mL'] for x in selected),max(x['left_pleural_volume_mL'] for x in selected)]})
 p=[x['period_s'] for x in cycles];pm=[x['pressure_mean'] for x in cycles];vm=[x['volume_mean'] for x in cycles];limits=plan['stability_candidate'];stats={'period_cv':statistics.pstdev(p)/statistics.mean(p),'pressure_mean_span':max(pm)-min(pm),'volume_mean_relative_span':(max(vm)-min(vm))/statistics.mean(vm)}
 stable=stats['period_cv']<=limits['period_cv_max'] and stats['pressure_mean_span']<=limits['cycle_mean_pressure_span_cmH2O_max'] and stats['volume_mean_relative_span']<=limits['cycle_mean_volume_span_over_mean_max']
 samples=rows[starts[-11]:starts[-1]];pv=[r['left_pleural_pressure_cmH2O'] for r in samples];vv=[r['left_pleural_volume_mL'] for r in samples];pad=.1*statistics.mean(vv)
 return {'cycles':cycles,'stability_statistics':stats,'candidate_stable':stable,'pressure_padded_candidate':[min(pv)-1,max(pv)+1],'volume_padded_candidate':[min(vv)-pad,max(vv)+pad],'reference_approved':False,'must_not_install_when_unstable':True,'phase_method':'complete inhale-to-inhale cycles; fixed last10, no interpolation or treatment-outcome fitting'}
