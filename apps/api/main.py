import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, FiniteFloat

from quantcore.derivatives.options import black_scholes
from quantcore.research.service import ResearchService, json_safe
from quantcore.security.access import AccessControl
from quantcore.statistics.research import statistical_report
from quantcore.valuation.dcf import DCFAssumptions, dcf, monte_carlo, sensitivity


class FactorRequest(BaseModel):
    weights: dict[str, FiniteFloat] | None = None
    sector_neutral: bool = False


class OptionRequest(BaseModel):
    spot: FiniteFloat = Field(gt=0, default=100)
    strike: FiniteFloat = Field(gt=0, default=100)
    years: FiniteFloat = Field(gt=0, le=30, default=1)
    rate: FiniteFloat = Field(ge=-.2, le=1, default=.05)
    volatility: FiniteFloat = Field(gt=0, le=5, default=.2)
    kind: Literal['call', 'put'] = 'call'


def create_app(directory=None, token=None):
    directory = directory or os.getenv('QUANTCORE_DATA_DIR', 'datasets')
    access = AccessControl(os.getenv('QUANTCORE_API_TOKEN', '') if token is None else token)
    origins = os.getenv('QUANTCORE_ALLOWED_ORIGINS', 'http://localhost:3100,http://127.0.0.1:3100,http://localhost:3000,http://127.0.0.1:3000').split(',')

    @asynccontextmanager
    async def lifespan(app):
        if os.getenv('QUANTCORE_MODE', 'demo') not in ('demo', 'research'):
            raise RuntimeError('only demo/research modes are supported')
        service = ResearchService(directory)
        await service.bootstrap()
        app.state.service = service
        yield
        service.store.engine.dispose()

    app = FastAPI(title='QuantCore', version='0.1.0', lifespan=lifespan)
    app.state.access = access
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['GET', 'POST'],
                       allow_headers=['Authorization', 'Content-Type'])

    @app.middleware('http')
    async def guard(request: Request, call_next):
        if request.url.path.startswith('/api/'):
            if not access.authorized(request.headers.get('authorization')):
                return JSONResponse({'detail': 'authentication required'}, status_code=401)
            client = request.client.host if request.client else 'unknown'
            if not access.allow(client):
                return JSONResponse({'detail': 'rate limit exceeded'}, status_code=429)
        service = getattr(app.state, 'service', None)
        if service:
            with service.metrics.measure('api'):
                response = await call_next(request)
            return response
        return await call_next(request)

    @app.exception_handler(KeyError)
    async def missing(request, error):
        return JSONResponse({'detail': 'unknown asset'}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({'detail': str(error)}, status_code=422)

    def respond(value):
        return JSONResponse(json_safe(value))

    @app.get('/health')
    def health():
        return {'status': 'ok', 'execution_mode': 'research', 'data_mode': 'synthetic'}

    @app.get('/api/overview')
    def overview():
        return respond(app.state.service.overview())

    @app.get('/api/assets/{symbol}/prices')
    def prices(symbol: str, limit: int = Query(252, ge=1, le=2000), as_of: datetime | None = None):
        return respond(app.state.service.prices(symbol, limit, as_of))

    @app.get('/api/assets/{symbol}/indicators')
    def indicators(symbol: str):
        return respond(app.state.service.indicators(symbol))

    @app.get('/api/assets/{symbol}/fundamentals')
    def fundamentals(symbol: str, as_of: datetime | None = None):
        return respond(app.state.service.fundamentals(symbol, as_of))

    @app.get('/api/factors')
    def factors(sector_neutral: bool = False):
        return respond(app.state.service.factors(sector_neutral=sector_neutral))

    @app.post('/api/factors')
    def weighted_factors(payload: FactorRequest):
        return respond(app.state.service.factors(payload.weights, payload.sector_neutral))

    @app.get('/api/backtests/{symbol}')
    def strategy(symbol: str, strategy: Literal['momentum', 'mean_reversion', 'buy_hold'] = 'momentum'):
        return respond(app.state.service.backtest(symbol, strategy))

    @app.get('/api/portfolio')
    def portfolio(method: Literal['equal_weight', 'minimum_variance', 'risk_parity'] = 'minimum_variance',
                  max_weight: float = Query(.4, gt=0, le=1)):
        return respond(app.state.service.portfolio(method, max_weight))

    @app.get('/api/ml/{symbol}')
    def ml(symbol: str):
        return respond(app.state.service.machine_learning(symbol))

    @app.get('/api/research/{symbol}')
    def research(symbol: str):
        return respond(app.state.service.research_report(symbol))

    @app.post('/api/valuation')
    def valuation(payload: DCFAssumptions):
        return respond({**dcf(payload), 'sensitivity': sensitivity(payload), 'monte_carlo': monte_carlo(payload)})

    @app.post('/api/options')
    def options(payload: OptionRequest):
        return respond(black_scholes(**payload.model_dump()))

    @app.get('/api/monitoring')
    def monitoring():
        return respond(app.state.service.monitoring())

    @app.get('/api/statistics')
    def statistics():
        return respond(statistical_report(app.state.service.returns()))

    @app.post('/api/ws-ticket')
    def ticket():
        return {'ticket': access.ticket(), 'expires_in_seconds': 30}

    @app.websocket('/ws/market')
    async def stream(websocket: WebSocket, ticket: str = ''):
        if websocket.headers.get('origin') not in origins or not access.consume(ticket):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        try:
            while True:
                start = time.perf_counter()
                await websocket.send_json(json_safe({'kind': 'dataset_snapshot', **app.state.service.overview()}))
                app.state.service.metrics.samples['websocket_send'].append((time.perf_counter()-start)*1000)
                await asyncio.sleep(5)
        except WebSocketDisconnect:
            pass

    return app


app = create_app()
