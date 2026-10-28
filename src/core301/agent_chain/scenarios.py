"""Host-owned scenario inputs and the replay available for each dataset."""
from core301.paths import PROJECT_ROOT

SCENARIOS = {
    'run_001': {'config_dir': 'config/medical_resources_v1', 'dataset_dir': 'dataset_v1/run_001',
                'replay_schedule': 'runs/medical_resources_deepseek_001/schedule.json'},
    'run_002': {'config_dir': 'config/medical_resources_v1_1', 'dataset_dir': 'dataset_v1/run_002',
                'replay_schedule': None},
}


def scenario_paths(name: str) -> dict:
    if name not in SCENARIOS:
        raise ValueError('Unknown scenario: ' + name)
    return {key: PROJECT_ROOT / value if value is not None else None
            for key, value in SCENARIOS[name].items()}
