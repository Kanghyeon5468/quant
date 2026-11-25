"""Actual local deployment plus demo-mode UI regression with an isolated TestClient."""
import json
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright

from apps.api.main import create_app


def main():
    checks, demo_checks, errors = [], [], []
    artifacts = Path('artifacts/actual_api')
    artifacts.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        options = {'channel': 'chrome'} if Path('/Applications/Google Chrome.app').exists() else {}
        browser = p.chromium.launch(**options)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:3100', wait_until='networkidle')
        expect(page.get_by_text('◉ ALPACA · HISTORICAL', exact=True)).to_be_visible()
        expect(page.get_by_text('Connected', exact=True)).to_be_visible(timeout=15000)
        expect(page.get_by_label('Asset', exact=True)).to_have_value('AAPL')
        assert page.get_by_label('Asset', exact=True).locator('option').all_text_contents() == ['AAPL', 'MSFT', 'NVDA', 'SPY', 'TSLA']
        expect(page.locator('canvas').first).to_be_visible()
        checks.append('actual_source_universe_chart_and_websocket')
        page.screenshot(path=str(artifacts/'actual-overview.png'), full_page=True)
        page.get_by_label('Asset', exact=True).select_option('TSLA')
        expect(page.get_by_text('TSLA · PRICE / USD')).to_be_visible()
        checks.append('actual_asset_selection')
        page.get_by_role('button', name='기업·가치평가').click()
        expect(page.get_by_text('Source: SEC CompanyFacts',exact=False)).to_be_visible()
        expect(page.get_by_role('cell',name='revenue_growth',exact=True)).to_be_visible()
        expect(page.get_by_role('button', name='DCF 계산')).to_have_count(0)
        checks.append('actual_sec_financials_no_demo_dcf')
        page.get_by_role('button', name='기술 분석').click()
        expect(page.get_by_role('cell', name='sma_60', exact=True)).to_be_visible()
        expect(page.locator('canvas').first).to_be_visible()
        checks.append('actual_indicators_and_paper_sma60')
        page.get_by_role('button', name='팩터 리서치').click()
        expect(page.get_by_role('cell',name='NVDA',exact=True)).to_be_visible()
        page.get_by_role('checkbox').check()
        expect(page.get_by_text('실제 GICS 섹터 자료가 없습니다. 프로젝트 리스크 그룹을 GICS로 대체하지 않습니다.')).to_be_visible()
        page.get_by_role('checkbox').uncheck()
        expect(page.get_by_role('cell',name='NVDA',exact=True)).to_be_visible()
        checks.append('actual_factors_and_unavailable_gics_no_substitute')
        page.get_by_role('button',name='뉴스·기관 공시').click()
        expect(page.get_by_text('실제 뉴스 · TSLA',exact=True)).to_be_visible()
        expect(page.get_by_text('VANGUARD GROUP INC · 오래된 보고서',exact=True)).to_be_visible()
        expect(page.get_by_text('공식 녹취록·허용 음성 수집 연결 없음.',exact=False)).to_be_visible()
        assert page.locator('a[target="_blank"]').count()>2
        page.screenshot(path=str(artifacts/'actual-information.png'),full_page=True)
        checks.append('actual_news_13f_links_stale_manager_and_missing_earnings')
        page.get_by_role('button', name='전략·백테스트').click()
        expect(page.get_by_text('NET TOTAL RETURN')).to_be_visible(timeout=30000)
        page.get_by_label('Strategy', exact=True).select_option('mean_reversion')
        expect(page.get_by_text('EXECUTION AUDIT')).to_be_visible(timeout=30000)
        expect(page.get_by_test_id('portfolio-replay')).to_be_visible()
        expect(page.get_by_role('cell', name='Momentum · 리스크 적용', exact=True)).to_be_visible()
        expect(page.get_by_test_id('walk-forward')).to_be_visible()
        expect(page.get_by_text('시간 순서대로 선택하고 이후 구간에서 검증',exact=True)).to_be_visible()
        expect(page.get_by_role('cell',name='최종 분리 구간',exact=True)).to_be_visible()
        checks.append('chronological_validation_periods_and_oos_chart')
        checks.append('whole_account_portfolio_replay')
        checks.append('actual_two_strategy_backtests')
        page.get_by_role('button', name='포트폴리오·리스크').click()
        expect(page.get_by_text('DAILY HISTORICAL VaR 95%')).to_be_visible()
        page.get_by_label('Optimizer', exact=True).select_option('risk_parity')
        expect(page.get_by_text('RISK CONTRIBUTION')).to_be_visible()
        checks.append('actual_portfolio_and_risk')
        page.get_by_role('button', name='머신러닝 검증').click()
        expect(page.get_by_role('cell', name='baseline_mean')).to_be_visible()
        checks.append('actual_ml_evaluation')
        page.get_by_role('button', name='시스템·설정').click()
        expect(page.get_by_role('cell', name='actual_market_data', exact=True)).to_be_visible()
        expect(page.get_by_test_id('paper-risk')).to_be_visible()
        checks.append('independent_live_paper_risk_report')
        page.get_by_role('button', name='모의투자 현황').click()
        expect(page.get_by_test_id('paper-performance')).to_be_visible()
        expect(page.get_by_text('PAPER · 실제 모의 계좌 실적', exact=True)).to_be_visible()
        live = page.request.get('http://127.0.0.1:3100/api/paper-performance').json()
        assert live['account']['equity'] == 100000 and live['pnl']['realized_gross'] == 0
        assert not live['stale'] and live['pnl']['ledger_status'] == 'reconciled'
        assert 'qcp1-' not in json.dumps(live) and 'account_id' not in json.dumps(live)
        checks.append('paper_actual_account_pnl_and_redacted_api')
        expect(page.get_by_test_id('corporate-actions')).to_be_visible()
        expect(page.get_by_role('cell',name='TECHNOLOGY',exact=True)).to_have_count(3)
        expect(page.get_by_role('cell',name='EQUITY_ETF',exact=True)).to_be_visible()
        expect(page.get_by_text('브로커 보유량 대사 완료',exact=False)).to_be_visible()
        checks.append('official_sic_groups_etf_and_corporate_reconciliation')
        expect(page.get_by_test_id('paper-no-fills')).to_be_visible()
        expect(page.get_by_role('cell', name='53', exact=True).first).to_be_visible()
        expect(page.get_by_role('cell', name='48', exact=True).first).to_be_visible()
        checks.append('paper_accepted_orders_not_claimed_as_fills')
        page.locator('details').first.locator('summary').click()
        expect(page.locator('details').first.get_by_text('기존 주문의 근거를 사후 복원', exact=False)).to_be_visible()
        checks.append('paper_order_signal_evidence_and_provenance')
        page.get_by_label('Paper history range').select_option('daily_history')
        expect(page.locator('canvas').first).to_be_visible()
        page.get_by_label('현재 예산으로 낸 주문만 보기').uncheck()
        expect(page.get_by_role('cell', name='취소', exact=True)).to_have_count(2)
        expect(page.get_by_text('동일 기간의 완료 일별 자료가 아직 없습니다.', exact=True)).to_be_visible()
        checks.append('paper_history_revision_filter_and_honest_comparison')
        page.screenshot(path=str(artifacts/'paper-performance.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'paper mobile overflow'
        page.set_viewport_size({'width': 1440, 'height': 1000})
        checks.append('paper_mobile_layout')
        page.get_by_role('button', name='EN', exact=True).click()
        page.keyboard.press('1')
        expect(page.locator('h1')).to_have_text('Market overview')
        checks.append('actual_monitor_language_and_keyboard')
        page.set_viewport_size({'width': 390, 'height': 844})
        page.screenshot(path=str(artifacts/'actual-mobile.png'), full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'mobile overflow'
        checks.append('actual_mobile_layout')
        page.close()
        # Exercise the same built frontend with an isolated demo API and mocked WS transport.
        # The deployed actual API and active paper scheduler are not reconfigured.
        with tempfile.TemporaryDirectory(prefix='quantcore-demo-ui-') as directory:
            with TestClient(create_app(directory=directory, data_source='demo', token='')) as demo:
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                page.on('pageerror', lambda error: errors.append(str(error)))
                def proxy(route):
                    request = route.request
                    url = urlsplit(request.url)
                    response = demo.request(request.method, url.path+('?' + url.query if url.query else ''),
                                            content=request.post_data, headers={'Content-Type': 'application/json'})
                    route.fulfill(status=response.status_code, content_type='application/json', body=response.text)
                page.route('**/api/**', proxy)
                page.route_web_socket('ws://127.0.0.1:8100/ws/market*',
                    lambda ws: ws.send(json.dumps({'kind': 'dataset_snapshot', **demo.get('/api/overview').json()})))
                page.goto('http://127.0.0.1:3100', wait_until='networkidle')
                expect(page.get_by_text('◉ DEMO · SYNTHETIC', exact=True)).to_be_visible()
                expect(page.get_by_label('Asset', exact=True)).to_have_value('QALPHA')
                demo_checks.append('demo_source_and_asset_registry')
                page.get_by_role('button', name='기업·가치평가').click()
                page.get_by_role('button', name='DCF 계산').click()
                expect(page.get_by_text('BASE VALUE / SHARE')).to_be_visible()
                demo_checks.append('demo_dcf_preserved')
                page.get_by_role('button', name='팩터 리서치').click()
                page.get_by_label('Momentum weight').fill('2')
                page.get_by_role('button', name='가중치 적용').click()
                expect(page.get_by_role('cell', name='QALPHA', exact=True)).to_be_visible()
                demo_checks.append('demo_factor_weights_preserved')
                page.get_by_role('button', name='전략·백테스트').click()
                expect(page.get_by_text('NET TOTAL RETURN')).to_be_visible()
                demo_checks.append('demo_backtest_preserved')
                page.get_by_role('button', name='모의투자 현황').click()
                expect(page.get_by_text('paper 실적은 Alpaca 모드에서 제공합니다.', exact=True)).to_be_visible()
                demo_checks.append('demo_does_not_expose_actual_paper_account')
                page.close()
        browser.close()
    assert not errors, errors
    report = {'actual_checks_passed': len(checks), 'actual_checks': checks,
              'demo_ui_checks_passed': len(demo_checks), 'demo_ui_checks': demo_checks,
              'demo_test_scope': 'same built frontend; isolated DemoProvider TestClient and intercepted WS',
              'actual_test_scope': 'running localhost Compose services; Alpaca historical snapshots',
              'browser_errors': errors}
    Path('docs/actual_api_browser_validation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
