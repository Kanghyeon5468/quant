"""Run against actual Compose services: python tests/end_to_end/browser.py."""
import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    artifacts = Path('artifacts')
    artifacts.mkdir(exist_ok=True)
    checks, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(os.getenv('QUANTCORE_WEB_URL', 'http://127.0.0.1:3100'), wait_until='networkidle')
        expect(page.locator('h1')).to_have_text('시장 개요')
        expect(page.get_by_text('Connected', exact=True)).to_be_visible(timeout=15000)
        expect(page.locator('canvas').first).to_be_visible()
        checks.append('overview_price_chart_and_websocket')
        page.screenshot(path=str(artifacts/'dashboard-desktop.png'), full_page=True)
        page.get_by_label('Asset', exact=True).select_option('QBETA')
        expect(page.get_by_text('QBETA · PRICE / USD')).to_be_visible()
        checks.append('asset_selection')
        page.get_by_role('button', name='기업·가치평가').click()
        page.get_by_role('button', name='DCF 계산').click()
        expect(page.get_by_text('BASE VALUE / SHARE')).to_be_visible()
        checks.append('valuation_compute')
        page.get_by_role('button', name='기술 분석').click()
        expect(page.get_by_text('RELATIVE STRENGTH INDEX')).to_be_visible()
        expect(page.locator('canvas').first).to_be_visible()
        checks.append('technical_indicators')
        page.get_by_role('button', name='팩터 리서치').click()
        page.get_by_label('Momentum weight').fill('2')
        page.get_by_role('button', name='가중치 적용').click()
        expect(page.get_by_role('cell', name='QBETA', exact=True)).to_be_visible()
        checks.append('factor_weights')
        page.get_by_role('button', name='전략·백테스트').click()
        expect(page.get_by_text('NET TOTAL RETURN')).to_be_visible(timeout=30000)
        page.get_by_label('Strategy', exact=True).select_option('mean_reversion')
        expect(page.get_by_text('EXECUTION AUDIT')).to_be_visible(timeout=30000)
        checks.append('two_strategy_views')
        page.get_by_role('button', name='포트폴리오·리스크').click()
        expect(page.get_by_text('DAILY HISTORICAL VaR 95%')).to_be_visible()
        page.get_by_label('Optimizer', exact=True).select_option('risk_parity')
        expect(page.get_by_text('RISK CONTRIBUTION')).to_be_visible()
        checks.append('portfolio_optimization')
        page.get_by_role('button', name='머신러닝 검증').click()
        expect(page.get_by_role('cell', name='baseline_mean')).to_be_visible()
        checks.append('ml_baseline_and_split_audit')
        page.get_by_role('button', name='시스템·설정').click()
        expect(page.get_by_text('SYSTEM OBSERVABILITY')).to_be_visible()
        page.get_by_role('button', name='EN', exact=True).click()
        expect(page.locator('h1')).to_have_text('System & settings')
        page.keyboard.press('1')
        expect(page.locator('h1')).to_have_text('Market overview')
        expect(page.locator('canvas').first).to_be_visible()
        checks.append('language_and_keyboard_navigation')
        page.set_viewport_size({'width': 390, 'height': 844})
        page.screenshot(path=str(artifacts/'dashboard-mobile.png'), full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'horizontal overflow'
        checks.append('mobile_layout')
        assert errors == [], errors
        browser.close()
    report = {'checks_passed': len(checks), 'checks': checks, 'browser_errors': errors,
              'target': 'actual local services', 'data_mode': 'synthetic'}
    Path('docs/browser_results.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
