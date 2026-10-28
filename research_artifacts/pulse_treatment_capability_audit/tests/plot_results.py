from pathlib import Path
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parent.parent
fig,axs=plt.subplots(2,2,figsize=(11,7),constrained_layout=True)
for name,label in [('baseline','Baseline'),('epi_low','Epi 1.25 ug'),('epi_high','Epi 5 ug'),('saline','Saline 60 mL/min'),('combo_high_AB','Epi 5 ug + Saline')]:
 rows=[{k:float(v) for k,v in x.items()} for x in csv.DictReader((R/'tests/raw'/name/'samples.csv').open())]
 for ax,key,unit in zip(axs.flat,['HeartRate','SystolicArterialPressure','BloodVolume','Epinephrine_ug_mL'],['1/min','mmHg','mL','ug/mL']):
  ax.plot([x['time_s'] for x in rows],[x[key] for x in rows],label=label,lw=1.5);ax.set_title(key);ax.set_xlabel('Simulation time (s)');ax.set_ylabel(unit);ax.grid(alpha=.2)
axs[0,0].legend(fontsize=8);fig.suptitle('Pulse 4.3.2 / Soldier — native controlled experiments')
fig.savefig(R/'physiology_comparison.png',dpi=160);fig.savefig(R/'physiology_comparison.svg')
