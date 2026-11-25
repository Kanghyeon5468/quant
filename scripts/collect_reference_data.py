"""Collect verified current security classifications and corporate events; GET only."""
import argparse
import json
from pathlib import Path

from quantcore.data.reference.securities import collect_reference
from quantcore.paper.client import PaperClient

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    client = PaperClient(args.env_file)
    try:
        result = collect_reference(Path(__file__).resolve().parents[1], args.env_file, client, force=args.force)
        print(json.dumps({'collected_at': result['manifest']['collected_at'],
            'securities': {s:{k:r[k] for k in ['name','sic','risk_group','asset_class','status']} for s,r in result['securities'].items()},
            'corporate_event_counts': {kind:sum(e['type']==kind for e in result['actions']) for kind in ['split','dividend','rename','unsupported']}},indent=2))
    finally:
        client.close()
