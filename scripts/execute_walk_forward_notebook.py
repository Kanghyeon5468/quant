"""Execute the saved chronological validation notebook. No broker or network access."""
import json
from datetime import datetime, timezone
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    path=ROOT/'notebooks/QuantCore_Walk_Forward_Validation.ipynb'
    notebook=nbformat.read(path,as_version=4)
    notebook.cells.append(nbformat.v4.new_code_cell('''
assert metadata['oos_sessions']==126 and len(report['decisions'])==3
assert all(r['audit']['cash_inventory_nav_reconciled'] and r['audit']['signal_before_fill'] for r in results.values())
assert len(set(r['strategy'] for r in results['selected_oos']['curve']))==3
assert all(d['validation'][-1]<d['test'][0] for d in report['decisions'])
'''))
    NotebookClient(notebook,kernel_name='quantcore-py312',timeout=120,
        resources={'metadata':{'path':str(ROOT/'notebooks')}}).execute(cleanup_kc=True)
    notebook.cells.pop()
    code=[c for c in notebook.cells if c.cell_type=='code']
    result={'executed_at':datetime.now(timezone.utc).isoformat(),'kernel':'quantcore-py312','code_cells':len(code),
        'png_outputs':sum('image/png' in o.get('data',{}) for c in code for o in c.outputs),
        'cell_errors':sum(o.output_type=='error' for c in code for o in c.outputs),'folds':3,'oos_sessions':126}
    assert result['png_outputs']==2 and not result['cell_errors']
    nbformat.write(notebook,path)
    (ROOT/'docs/walk_forward_notebook_validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
