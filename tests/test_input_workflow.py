"""在临时目录验证收件、结果输出和成功归档，不触碰项目真实实验数据。"""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
import mfl_analysis as app


def run(project, extra=()):
    with patch.object(app, '__file__', str(project/'mfl_analysis.py')), patch.object(sys, 'argv', ['mfl_analysis.py', *extra]):
        try:
            app.main()
        except SystemExit as exc:
            assert exc.code == 1
            return 1
    return 0


def summary(project):
    return pd.read_csv(sorted((project/'output').glob('batch_summary_*.csv'))[-1])


def stub(args, destination):
    if Path(args.input).stem == 'bad':
        raise ValueError('Simulated signal validation failure')
    destination.mkdir(parents=True, exist_ok=True)
    (destination/'processed_signals.csv').write_text('pos,f9_processed\n1,0\n')
    return {'rows': 1, 'candidates': []}


with tempfile.TemporaryDirectory() as temporary:
    project = Path(temporary)
    assert run(project) == 0
    assert all((project/name).is_dir() for name in ('input', 'input_pre', 'output'))
    inbox = project/'input'
    header = 'ts,pos,' + ','.join(f'f{i}' for i in range(9,16)) + '\n'
    for name in ('good.csv', 'second.CSV', 'bad.csv'):
        (inbox/name).write_text(header)
    (inbox/'labels.csv').write_text('defect_id,pos\none,100\n')
    (project/'input_pre'/'good.csv').write_text('previous experiment')
    (project/'output'/'ignored.csv').write_text(header)
    (inbox/'nested').mkdir()
    (inbox/'nested'/'ignored.csv').write_text(header)
    with patch.object(app, 'process_file', side_effect=stub) as process:
        assert run(project) == 1
        assert process.call_count == 3
    report = summary(project)
    assert sorted(report.status) == ['failed', 'skipped', 'success', 'success']
    assert (inbox/'bad.csv').exists() and (inbox/'labels.csv').exists()
    assert not (inbox/'good.csv').exists() and not (inbox/'second.CSV').exists()
    assert (project/'input_pre'/'good.csv').read_text() == 'previous experiment'
    assert (project/'input_pre'/'good_1.csv').read_text() == header
    for row in report[report.status == 'success'].itertuples():
        assert app.file_digest(Path(row.archived_file)) == row.source_sha256
    with patch.object(app, 'process_file', side_effect=stub) as process:
        assert run(project) == 1
        assert process.call_count == 1  # successful inputs are no longer scanned
    (inbox/'archive_error.csv').write_text(header)
    with patch.object(app, 'process_file', side_effect=stub), patch.object(app, 'archive_input', side_effect=PermissionError('locked')):
        assert run(project, [str(inbox/'archive_error.csv')]) == 1
    report = summary(project)
    assert report.iloc[0].status == 'archive_failed'
    assert (inbox/'archive_error.csv').exists()
    assert not (Path(report.iloc[0].output_directory)/'FAILED.txt').exists()
    expected = app.file_digest(inbox/'archive_error.csv')
    (inbox/'archive_error.csv').write_text('changed input')
    try:
        app.archive_input(inbox/'archive_error.csv', inbox, project/'input_pre', expected)
        raise AssertionError('changed input must not be archived')
    except ValueError:
        assert (inbox/'archive_error.csv').exists()
    external = project/'external'
    external.mkdir()
    (external/'signal.csv').write_text(header)
    with patch.object(app, 'process_file', side_effect=stub):
        assert run(project, [str(external)]) == 0
    assert (external/'signal.csv').exists()
    assert not (external/'output').exists()

# Real signal processing: verify CSV + waveform output and byte-preserving archive.
with tempfile.TemporaryDirectory() as temporary:
    project = Path(temporary)
    (project/'input').mkdir()
    source = project/'input'/'真实流程.csv'
    pos = np.arange(20., 701.)
    pulse = 5*np.exp(-.5*((pos-300)/8)**2)
    data = {'ts': pd.date_range('2026-01-01', periods=len(pos), freq='10ms'), 'pos': pos}
    data.update({f'f{i}': i + pos*.001 + pulse for i in range(9,16)})
    pd.DataFrame(data).to_csv(source, index=False)
    expected = app.file_digest(source)
    assert run(project) == 0
    report = summary(project)
    assert report.iloc[0].status == 'success'
    destination = Path(report.iloc[0].output_directory)
    assert (destination/'processed_signals.csv').stat().st_size > 0
    assert (destination/'processing_comparison.png').stat().st_size > 0
    assert app.file_digest(Path(report.iloc[0].archived_file)) == expected
    assert not source.exists()
    with patch.object(app, 'process_file') as process:
        assert run(project) == 0
        process.assert_not_called()

print('PASS: input/output/input_pre workflow, collisions, failures, repeat run, real CSV and plot')
