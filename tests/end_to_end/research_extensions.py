"""Exercise deployed research controls with existing actual snapshots and pure assumptions."""
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    with sync_playwright() as playwright:
        options = {"channel": "chrome"} if Path("/Applications/Google Chrome.app").exists() else {}
        browser = playwright.chromium.launch(**options)
        page = browser.new_page(viewport={"width": 1400, "height": 940})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:3100", wait_until="domcontentloaded")
        page.get_by_role("button", name="연구 도구").click()
        lab = page.get_by_test_id("research-lab")
        selector = lab.get_by_label("연구 도구", exact=True)
        expect(lab.get_by_text("미 국채 10년물", exact=False).last).to_be_visible()
        lab.get_by_role("button", name="KRW 환산").click()
        expect(lab.get_by_text("KRW/USD", exact=False).last).to_be_visible()
        expect(lab.get_by_role("link", name="Federal Reserve", exact=True)).to_be_visible()
        lab.get_by_role("button", name="도구 고정").click()
        selector.select_option("crypto")
        expect(lab.get_by_text("Coinbase Exchange", exact=False).first).to_be_visible()
        expect(lab.get_by_role("columnheader", name="매수 호가 (USD)")).to_be_visible()
        lab.get_by_role("button", name="실시간 연결").click()
        expect(lab.get_by_role("columnheader", name="실시간 매수 (USD)")).to_be_visible(timeout=20000)
        expect(lab.get_by_text("실시간 관측 체결", exact=True)).to_be_visible(timeout=20000)
        lab.get_by_role("button", name="실시간 중지").click()
        selector.select_option("options")
        lab.get_by_role("button", name="옵션 계산").click()
        expect(lab.get_by_role("cell", name="delta", exact=True)).to_be_visible()
        lab.get_by_text("거시경제 · 환율", exact=True).last.click()
        expect(lab.get_by_role("heading", name="미국 거시 지표 · 환율")).to_be_visible()
        selector.select_option("valuation")
        expect(lab.get_by_role("cell", name="P/E", exact=True)).to_be_visible()
        lab.get_by_label("평가 모델").select_option("wacc")
        lab.get_by_role("button", name="가치 계산").click()
        expect(lab.get_by_role("cell", name="cost_of_equity", exact=True)).to_be_visible()
        selector.select_option("technical")
        lab.get_by_label("시간봉").select_option("weekly")
        expect(lab.locator("canvas").first).to_be_visible(timeout=25000)
        selector.select_option("factors")
        expect(lab.get_by_role("columnheader", name="ICIR")).to_be_visible()
        expect(lab.get_by_role("columnheader", name="중립화 점수")).to_be_visible()
        selector.select_option("statistics")
        expect(lab.get_by_role("cell", name="cointegration", exact=True)).to_be_visible(timeout=25000)
        selector.select_option("ml")
        expect(lab.get_by_role("cell", name="random_forest", exact=True).first).to_be_visible(timeout=25000)
        selector.select_option("brief")
        expect(lab.get_by_text("반대 가설", exact=False).first).to_be_visible()
        selector.select_option("basket")
        expect(lab.get_by_text("63거래일", exact=False)).to_be_visible(timeout=40000)
        selector.select_option("imports")
        expect(lab.get_by_role("heading", name="로컬 시장 데이터")).to_be_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors, errors
        print("11 research tools, pinned panel, mobile layout and page error checks passed")


if __name__ == "__main__":
    main()
