"""Exclusive run directories, JSON snapshots and a final file digest inventory."""
import hashlib
from importlib.metadata import distributions
import json
from pathlib import Path
import re
import subprocess

from core301.paths import PROJECT_ROOT
from .scenarios import SCENARIOS, scenario_paths

RESULTS_ROOT = PROJECT_ROOT / 'experiments/results/agent_chain'
KNOWN_SIMPLIFICATIONS = [
    'Patients excluded by the treatment agent are absent from dispatch input and consume no scheduling '
    'resources. They still enter physiology simulation without treatment and are included in outcomes.',
    'Decisions use dataset Pulse observations sampled about two minutes after injury, '
    'not the execution engines. Patients arriving at minutes 10 and 20 use those same '
    'dataset observations. V2 event-driven decisions will read running engines.',
    'Hemothorax single-injury research is BLOCKED in protocol_book.SPECIALTY_DECISIONS '
    'because negative residual blood volume and the drainage endpoint are unresolved. '
    'V1 borrows the fixed V2.1 composite-runtime payloads; P07 and P16 are exploratory.',
    'Dehydration is an initialization condition present from engine startup, including '
    'the 60-second stabilization period. Its injury clock starts after stabilization; '
    'other injuries are applied dynamically only after stabilization.',
]


def write_json(path: Path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_error(exc: Exception) -> dict:
    # SDK exception messages/headers can contain credentials or gateway URLs.
    return {'error_type': type(exc).__name__, 'status_code': getattr(exc, 'status_code', None)}


def create_run(run_id: str, mode: str, providers: dict, config: dict,
               root: Path = RESULTS_ROOT, *, scenario: str = 'run_001') -> Path:
    paths = scenario_paths(scenario)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', run_id):
        raise ValueError('run_id must be a single safe directory name')
    directory = Path(root) / run_id
    directory.mkdir(parents=True, exist_ok=False)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=PROJECT_ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=PROJECT_ROOT, text=True))
    write_json(directory / 'manifest.json', {
        'run_id': run_id, 'mode': mode, 'commit': commit, 'working_tree_dirty': dirty,
        'scenario': scenario, 'config_dir': SCENARIOS[scenario]['config_dir'],
        'dataset_dir': SCENARIOS[scenario]['dataset_dir'],
        'scenario_files_sha256': {
            str(path.relative_to(PROJECT_ROOT)): sha256(path.read_bytes())
            for key in ('config_dir', 'dataset_dir')
            for path in sorted(paths[key].rglob('*')) if path.is_file()
        },
        'parameters': config, 'providers': providers,
        'dependencies': dict(sorted((d.metadata['Name'], d.version) for d in distributions()
                                    if d.metadata.get('Name'))),
        'known_simplifications': KNOWN_SIMPLIFICATIONS,
    })
    return directory


def snapshot(state: dict, node: str, changes: dict) -> dict:
    write_json(Path(state['run_dir']) / 'state' / f'{node}.json', {**state, **changes})
    return changes


def finish_run(directory: Path, summary: dict):
    write_json(directory / 'summary.json', summary)
    write_json(directory / 'sha256_manifest.json', {
        str(path.relative_to(directory)): sha256(path.read_bytes())
        for path in sorted(directory.rglob('*'))
        if path.is_file() and path.name != 'sha256_manifest.json'
    })
