"""Validate a persisted manual request without depending on orchestration or execution."""
import json

import pandas as pd

from quantcore.data.calendar import sessions
from quantcore.data.providers.alpaca import SYMBOLS
from quantcore.paper.client import PaperError
from quantcore.paper.journal import number


def authorized_reference(journal, request_id, cutoff, is_open):
    exists = journal.db.execute("SELECT 1 FROM sqlite_master WHERE name='manual_rebalances'").fetchone()
    row = journal.db.execute('SELECT revision,state,data FROM manual_rebalances WHERE request_id=?', (request_id,)).fetchone() if exists else None
    if not row or row[1] != 'prepared':
        raise PaperError('manual re-entry requires a durable explicitly authorized request')
    data = json.loads(row[2])
    day = cutoff.tz_convert('America/New_York').date()
    schedule = sessions(day, day)
    if (not is_open or schedule.empty or data['session'] != str(day)
            or not schedule.iloc[0]['open'] <= cutoff < schedule.iloc[0]['close']-pd.Timedelta(minutes=2)
            or pd.Timestamp(data['collected_at']) > cutoff or data.get('source') != 'alpaca-iex-regular-1min'
            or set(data['references']) != set(SYMBOLS)):
        raise PaperError('manual execution references are unavailable or from the future')
    for ref in data['references'].values():
        end = pd.Timestamp(ref['bar_end'])
        if (not schedule.iloc[0]['open'] < end <= cutoff-pd.Timedelta(minutes=1)
                or cutoff-end > pd.Timedelta(minutes=5) or number(ref['price']) <= 0):
            raise PaperError('manual execution price is stale, invalid or incomplete')
    return {**{k:v for k,v in data.items() if k != 'raw_pages'}, 'revision':row[0]}
