"""Execute the saved portfolio report notebook; no market requests or broker access."""
import json
from datetime import datetime, timezone
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]


def main():
    path = ROOT/'notebooks/QuantCore_Portfolio_Paper_Backtest.ipynb'
    notebook = nbformat.read(path, as_version=4)
    notebook.cells.append(nbformat.v4.new_code_cell('''
assert len(results) == 4
assert all(r['audit']['signal_before_fill'] and r['audit']['limit_respected'] for r in results.values())
assert all(r['audit']['cash_inventory_nav_reconciled'] and r['audit']['sessions'] == 252 for r in results.values())
assert metadata['regular_minute_rows'] == 683312
assert results['momentum_risk_net']['config']['budget'] == '100000'
'''))
    NotebookClient(notebook, kernel_name='quantcore-py312', timeout=120,
                   resources={'metadata': {'path': str(ROOT/'notebooks')}}).execute(cleanup_kc=True)
    notebook.cells.pop()
    code = [c for c in notebook.cells if c.cell_type == 'code']
    report = {'executed_at': datetime.now(timezone.utc).isoformat(), 'kernel': 'quantcore-py312',
              'code_cells': len(code), 'png_outputs': sum('image/png' in o.get('data', {}) for c in code for o in c.outputs),
              'cell_errors': sum(o.output_type == 'error' for c in code for o in c.outputs),
              'actual_scenarios': 4, 'sessions_per_scenario': 252}
    assert report['png_outputs'] == 2 and not report['cell_errors']
    nbformat.write(notebook, path)
    (ROOT/'docs/portfolio_notebook_validation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
