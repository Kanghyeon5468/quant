import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import nbformat
from jupyter_client import KernelManager
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT/'notebooks/QuantCore_Real_Stocks_Backtest.ipynb'
AUDIT = '''
assert set(market['mode']) == {'historical'}
assert len(FRAMES) == 5 and len(RESULTS) == 15 and len(VALIDATION) == 15
assert 'matched 15' in reference_status
assert VALIDATION.cash_inventory_nav_reconciled.all() and VALIDATION.future_mutation_invariant.all()
show_detail('NVDA', 'mean_reversion')
asset_picker.value = 'TSLA'
strategy_picker.value = 'mean_reversion'
detail_button.click()
asset_picker.value, strategy_picker.value = SYMBOL, STRATEGY
detail_output.clear_output()
print('REAL_NOTEBOOK_AUDIT='+json.dumps({
    'python': sys.executable, 'numpy': np.__version__, 'data_mode': 'historical',
    'symbols': sorted(FRAMES), 'comparisons': len(RESULTS), 'daily_rows': len(market),
    'input_sha256': input_hash, 'code_sha256': EXPERIMENT['code_sha256'], 'reference': reference_status,
    'period': RESULTS[SYMBOL, STRATEGY]['period'], 'widget_and_other_symbol_checked': True,
}))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kernel-python')
    parser.add_argument('--no-save', action='store_true')
    parser.add_argument('--report', default='docs/real_notebook_validation.json')
    args = parser.parse_args()
    notebook = nbformat.read(PATH, as_version=4)
    for cell in notebook.cells:
        if cell.cell_type == 'code':
            cell.outputs, cell.execution_count = [], None
    notebook.cells.append(nbformat.v4.new_code_cell(AUDIT))
    manager = KernelManager(kernel_name='quantcore-py312')
    if args.kernel_python:
        manager.kernel_spec.argv[0] = str(Path(args.kernel_python).absolute())
    NotebookClient(notebook, km=manager, kernel_name='quantcore-py312', timeout=180, store_widget_state=True,
        resources={'metadata': {'path': str(ROOT/'notebooks')}}).execute(cleanup_kc=True)
    audit = notebook.cells.pop()
    lines = ''.join(o.get('text', '') for o in audit.outputs if o.output_type == 'stream').splitlines()
    report = json.loads(next(line for line in lines if line.startswith('REAL_NOTEBOOK_AUDIT=')).split('=', 1)[1])
    report.update(executed_at=datetime.now(timezone.utc).isoformat(),
        code_cells=sum(c.cell_type == 'code' for c in notebook.cells),
        png_outputs=sum('image/png' in o.get('data', {}) for c in notebook.cells for o in c.get('outputs', [])),
        cell_errors=sum(o.output_type == 'error' for c in notebook.cells for o in c.get('outputs', [])))
    assert report['cell_errors'] == 0 and report['png_outputs'] >= 5
    if args.kernel_python:
        assert Path(report['python']).absolute() == Path(args.kernel_python).absolute()
    if not args.no_save:
        notebook.metadata.pop('widgets', None)
        for cell in notebook.cells:
            for output in cell.get('outputs', []):
                output.get('data', {}).pop('application/vnd.jupyter.widget-view+json', None)
        nbformat.validate(notebook)
        nbformat.write(notebook, PATH)
    (ROOT/args.report).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
