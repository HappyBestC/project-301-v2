import native_audit as n,json
out=n.ROOT/'raw'/'batch_partial';out.mkdir(exist_ok=False)
e=n.PyPulse.Engine(n.PyPulse.model_type.human_adult_whole_body,str(n.DATA));e.log_to_console(False);e.set_log_filename(str(out/'pulse.log'))
r={'initialized':e.serialize_from_file(str(n.DATA/'states/Soldier@0s.json'),json.dumps({'DataRequest':n.req}),n.F)}
a=[n.saline(),n.pa('SubstanceBolus',Substance='Epinephrine',Concentration=n.scalar('MassPerVolume',1,'ug/mL')),n.oxy()]
r['input']=a;r['before_time_s']=list(e.pull_data())[0];r['accepted']=e.process_actions(json.dumps({'AnyAction':a}),n.F);r['after_time_s']=list(e.pull_data())[0]
s=json.loads(e.serialize_to_string(n.F));r['active_after_submit']=s.get('ActiveActions');r['advance_ok']=e.advance_timestep();r['after_advance_time_s']=list(e.pull_data())[0]
(out/'events.json').write_text(json.dumps(r,indent=2));e.clear();print(json.dumps(r))
