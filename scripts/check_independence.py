"""Run with .venv/bin/python -I from any directory; deny all reads of the old tree."""
from pathlib import Path
import os,sys,json,pkgutil,importlib
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT.with_name('project-301')
def audit(event,args):
    if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
        p=Path(os.fsdecode(args[0])).resolve()
        if p.is_relative_to(OLD):raise RuntimeError('OLD_PROJECT_ACCESS:'+str(p))
sys.addaudithook(audit)
import core301
mods={}
for info in pkgutil.walk_packages(core301.__path__,core301.__name__+'.'):
    m=importlib.import_module(info.name)
    assert Path(m.__file__).resolve().is_relative_to(ROOT/'src')
    mods[info.name]=str(Path(m.__file__).relative_to(ROOT))
from core301.dispatch.shared_resources.catalog import Catalog
c=Catalog();assert len(c.singles)==10 and len(c.composites)==5 and len(c.requirements)==12
from core301.runtime.v2.restricted_admission import verify_admission
for k in ['hemothorax','carbon_monoxide_exposure','environmental_hypoxia']:verify_admission(k)
from core301.runtime.v2_1.admission import ADMITTED,verify_admission
for k in ADMITTED:verify_admission(k)
assert not any(Path(p).resolve().is_relative_to(OLD) for p in sys.path if p)
print(json.dumps({'cwd':str(Path.cwd()),'isolated':sys.flags.isolated,'python':sys.executable,'sys_path':sys.path,'modules':mods,'single_profiles':len(c.singles),'composite_profiles':len(c.composites),'actions':sorted(c.requirements),'admission_checks':8,'old_tree_open_policy':'DENIED','external_pulse':str((ROOT/'pulse').resolve())},indent=2))
