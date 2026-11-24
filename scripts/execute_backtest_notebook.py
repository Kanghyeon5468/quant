"""Execute the actual notebook and audit outputs without changing its input files."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import nbformat
from jupyter_client import KernelManager
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / 'notebooks/QuantCore_Backtest.ipynb'
AUDIT = '''
audit = {
    'scenario': SCENARIO_NAME, 'python': sys.executable, 'numpy': np.__version__, 'pandas': pd.__version__,
    'rows': len(market), 'assets': len(FRAMES), 'strategy_comparisons': len(RESULTS),
    'config': CONFIG.model_dump(), 'symbol': SYMBOL, 'strategy': STRATEGY,
    'reference_check': reference_status, 'input_origin': input_origin, 'input_sha256': input_hash,
    'selected_net_return': SELECTED['metrics']['total_return'],
    'evaluation_rows': len(SELECTED['curve']),
}
asset_picker.value = 'QBETA'
strategy_picker.value = 'mean_reversion'
detail_button.click()
asset_picker.value, strategy_picker.value = SYMBOL, STRATEGY
detail_output.clear_output()
assert len(RESULTS) == 18 and len(market) == 4680
assert len(SELECTED['curve']) == CONFIG.evaluation_bars
print('QUANTCORE_NOTEBOOK_AUDIT='+json.dumps(audit))
'''


def execute(scenario, kernel_python=None, save_notebook=True):
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    for cell in notebook.cells:
        if cell.cell_type != 'code':
            continue
        cell.outputs, cell.execution_count = [], None
        if scenario == 'fallback':
            cell.source = cell.source.replace('if price_path.exists():', 'if False:  # Audit in-memory fallback')
        if scenario != 'default':
            cell.source = cell.source.replace('EXPORT_RESULTS = True', 'EXPORT_RESULTS = False')
        if scenario == 'custom':
            cell.source = cell.source.replace("SYMBOL = 'QALPHA'", "SYMBOL = 'QBETA'")
            cell.source = cell.source.replace("STRATEGY = 'momentum'", "STRATEGY = 'mean_reversion'")
            cell.source = cell.source.replace('evaluation_bars=252', 'evaluation_bars=126')
            cell.source = cell.source.replace('commission_bps=1,', 'commission_bps=2,')
    notebook.cells.append(nbformat.v4.new_code_cell(f'SCENARIO_NAME = {scenario!r}\n'+AUDIT))
    manager = KernelManager(kernel_name='quantcore-py312')
    if kernel_python:
        interpreter = Path(kernel_python).absolute()
        if not interpreter.is_file():
            raise ValueError('kernel Python does not exist')
        manager.kernel_spec.argv[0] = str(interpreter)
    NotebookClient(notebook, km=manager, timeout=180, kernel_name='quantcore-py312',
                   resources={'metadata': {'path': str(ROOT / 'notebooks')}}, store_widget_state=True).execute(cleanup_kc=True)
    audit_cell = notebook.cells.pop()
    stream = ''.join(o.get('text', '') for o in audit_cell.outputs if o.output_type == 'stream')
    marker = next(line for line in stream.splitlines() if line.startswith('QUANTCORE_NOTEBOOK_AUDIT='))
    audit = json.loads(marker.split('=', 1)[1])
    if kernel_python:
        assert Path(audit['python']).absolute() == Path(kernel_python).absolute()
    audit['code_cells'] = sum(c.cell_type == 'code' for c in notebook.cells)
    audit['png_outputs'] = sum('image/png' in o.get('data', {}) for c in notebook.cells for o in c.get('outputs', []))
    audit['errors'] = sum(o.output_type == 'error' for c in notebook.cells for o in c.get('outputs', []))
    assert audit['errors'] == 0 and audit['png_outputs'] >= 5
    if scenario == 'default' and save_notebook:
        reference_file = ROOT / 'docs/research_results.json'
        if reference_file.exists() and audit['input_sha256'] == json.loads(reference_file.read_text())['dataset']['sha256']:
            assert 'matched 12' in audit['reference_check']
        # Static graphs remain visible; controls activate when the user runs the cell.
        notebook.metadata.pop('widgets', None)
        for cell in notebook.cells:
            for output in cell.get('outputs', []):
                output.get('data', {}).pop('application/vnd.jupyter.widget-view+json', None)
        nbformat.validate(notebook)
        nbformat.write(notebook, NOTEBOOK)
    print(json.dumps(audit, ensure_ascii=False))
    return audit


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-alternatives', action='store_true')
    parser.add_argument('--kernel-python', help='Test a selected interpreter without changing the registered kernel.')
    parser.add_argument('--no-save', action='store_true', help='Leave notebook source and saved outputs unchanged.')
    parser.add_argument('--report', default='docs/notebook_validation.json')
    args = parser.parse_args()
    scenarios = ['default', 'fallback', 'custom'] if args.check_alternatives else ['default']
    records = [execute(scenario, args.kernel_python, not args.no_save) for scenario in scenarios]
    report = {'executed_at': datetime.now(timezone.utc).isoformat(), 'kernel': 'quantcore-py312',
              'kernel_python_override': args.kernel_python,
              'notebook': str(NOTEBOOK.relative_to(ROOT)), 'data_mode': 'synthetic', 'scenarios': records}
    (ROOT / args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
