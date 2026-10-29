import csv
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from core301.paths import PROJECT_ROOT
from core301.standard_answer.deficit import minute_values, cumulative_deficit


def test_exact_fractional_interpolation_terminal_zero_and_missing_propagation():
    samples = [{'time_min': 0, 'co': 4}, {'time_min': 2, 'co': 2}, {'time_min': 3.5, 'co': 1}]
    values = minute_values(samples, 'co', 3.5, True)
    assert values[:5] == pytest.approx([4, 3, 2, 4/3, 0])
    assert cumulative_deficit([5] * 121, [3] * 121)[120] == 240
    assert cumulative_deficit([5] * 121, minute_values(samples, 'co', None, True))[4] is None


def test_probe_imports_shared_functions():
    spec = importlib.util.spec_from_file_location('probe_shared_test', PROJECT_ROOT / 'scripts/curve_probe.py')
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    assert probe.minute_values is minute_values
    assert probe.cumulative_deficit is cumulative_deficit


def test_regression_against_existing_native_probe_outputs():
    root = PROJECT_ROOT / 'runs/curve_probe_001'
    reference_file = root / 'runs/reference_healthy/samples.csv'
    if not reference_file.exists():
        pytest.skip('Existing curve_probe_001 native evidence is not installed')
    def rows(path):
        with path.open() as handle:
            return list(csv.DictReader(handle))
    reference = minute_values(rows(reference_file), 'CardiacOutput_L_min', None, False)
    # Original pre-extraction implementation is independent of the new import.
    source = subprocess.check_output(['git', 'show', '9e6e191:scripts/curve_probe.py'], cwd=PROJECT_ROOT, text=True)
    namespace = {'HORIZON_MIN': 120}
    exec(source[source.index('def minute_values('):source.index('\n\nFIELDS =')], namespace)
    checked = 0
    for execution_file in sorted((root / 'runs').glob('*/untreated/execution.json')):
        record = json.loads(execution_file.read_text())
        if not record['reached_horizon'] and record['terminal_event'] is None:
            continue
        terminal = record['terminal_event']['time_min'] if record['terminal_event'] else None
        samples = rows(execution_file.with_name('samples.csv'))
        old = namespace['cumulative_deficit'](reference, namespace['minute_values'](samples, 'CardiacOutput_L_min', terminal, True))
        new = cumulative_deficit(reference, minute_values(samples, 'CardiacOutput_L_min', terminal, True))
        assert new == old
        for table in (root / 'tables').glob(execution_file.parent.parent.name + '*__cum_deficit_L.csv'):
            row = next((r for r in rows(table) if r['d'] == 'untreated'), None)
            if row and row['m120']:
                assert new == [float(row[f'm{i}']) for i in range(121)]
        checked += 1
    assert checked > 0
