import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from quantcore.research.service import json_safe
from quantcore.security.access import AccessControl


@pytest.fixture(scope='module')
def client(tmp_path_factory):
    app = create_app(tmp_path_factory.mktemp('api'), token='test-only-token')
    with TestClient(app, headers={'Authorization': 'Bearer test-only-token'}) as client:
        yield client


@pytest.mark.parametrize('path', ['/health', '/api/overview', '/api/assets/QALPHA/prices',
    '/api/assets/QALPHA/indicators', '/api/assets/QALPHA/fundamentals', '/api/factors',
    '/api/backtests/QALPHA?strategy=momentum', '/api/backtests/QALPHA?strategy=mean_reversion',
    '/api/portfolio?method=minimum_variance', '/api/portfolio?method=risk_parity',
    '/api/ml/QALPHA', '/api/research/QALPHA', '/api/monitoring', '/api/statistics'])
def test_real_api_routes(client, path):
    response = client.get(path)
    assert response.status_code == 200, response.text
    json.loads(response.text, parse_constant=lambda s: pytest.fail('nonfinite JSON '+s))


def test_auth_validation_and_unknown(client):
    assert client.get('/api/overview', headers={'Authorization': ''}).status_code == 401
    assert client.get('/api/assets/UNKNOWN/prices').status_code == 404
    assert client.get('/api/assets/QALPHA/prices?limit=0').status_code == 422
    assert client.get('/api/assets/QALPHA/prices?as_of=2023-01-01T00:00:00Z').json()['prices'] == []
    assert client.get('/api/portfolio?max_weight=.1').status_code == 422
    assert client.post('/api/valuation', json={'wacc': .01, 'terminal_growth': .03}).status_code == 422
    assert client.post('/api/valuation', json={'growth': .1}).status_code == 200
    assert client.post('/api/options', json={}).json()['price'] == pytest.approx(10.450583572185565)
    assert client.post('/api/factors', json={'weights': {'momentum': 2}}).status_code == 200
    assert client.post('/api/factors', json={'weights': {'momentum': -1}}).status_code == 422


def test_websocket_one_use_ticket(client):
    ticket = client.post('/api/ws-ticket').json()['ticket']
    with client.websocket_connect('/ws/market?ticket='+ticket, headers={'Origin': 'http://localhost:3000'}) as websocket:
        message = websocket.receive_json()
        assert message['kind'] == 'dataset_snapshot' and message['mode'] == 'synthetic'
    with pytest.raises(Exception):
        with client.websocket_connect('/ws/market?ticket='+ticket, headers={'Origin': 'http://localhost:3000'}):
            pass


def test_security_limits_and_safe_json():
    access = AccessControl('secret', limit=2)
    assert access.authorized('Bearer secret') and not access.authorized('Bearer other')
    assert access.allow('client') and access.allow('client') and not access.allow('client')
    ticket = access.ticket()
    assert access.consume(ticket) and not access.consume(ticket)
    assert json_safe({'missing': float('nan'), 'v': np.float64(2), 'at': pd.Timestamp('2025-01-01T00:00:00Z')}) == {
        'missing': None, 'v': 2., 'at': '2025-01-01T00:00:00+00:00'}
