# 실제 미국 종목 백테스트 · 2026-11-25

Alpaca의 실제 과거 시세를 사용한 **historical replay / 모의 매매**다. 실계좌 수익, 주문 체결 확인 또는 향후 수익 보장이 아니다. 기존 합성 실험과 자료·결과를 분리했다.

## 자료와 수집

- AAPL, MSFT, NVDA, TSLA, SPY. SPY는 ETF다. 현재 선택한 대형주/ETF 묶음이며 과거 전체 투자 가능 종목 집합이 아니다.
- 2025-07-01~2026-11-24, XNYS354세션, 일봉1,770행. 2026-11-25 수집.
- Alpaca IEX raw1분봉698,235개 중 정규장683,312개를 집계했다. 날짜·휴장·DST·조기 폐장은 exchange_calendars의 XNYS로 처리한다.
- 일봉 API의 자정 라벨을 체결 시각으로 사용하지 않았다. NY 정규장 open≤minute start 및 minute end≤close 조건을 적용하고 실제 첫/마지막 관측1분봉으로 일봉 O/C를 구성했다.
- 모든5종목이354개 세션을 확보했다. 첫 관측1분봉 시작과 개장 경계, 마지막1분봉 끝과 마감 경계의 차이는 이번 자료에서 모두0초다. 이는 공식 개장/종가 경매와 가격이 같다는 뜻은 아니다.
- `feed=iex`, `adjustment=raw`, GET `/v2/stocks/bars`, GET `/v1/corporate-actions`. 페이지 토큰·중복·OHLC·시각·완료 세션·해시를 검사한다. 401/403/429에서 중단하며 접근 제한을 우회하지 않는다.
- 기업행사 응답25건 중 구간 내 유효한 배당22건(AAPL6/MSFT6/NVDA5/SPY5, TSLA0)을 사용한다. 나머지 구간 밖 ex-date는 적용하지 않는다. 구간 내 split은0건이다.
- raw API 페이지·Parquet·기업행사·calendar와 SHA-256은 ignored `datasets/real_equities/`의 동결본에 저장한다. 원시 시세/체결가격은 외부 재배포하지 않는다. 키는 사용자가 승인한 기존 환경 파일에서 읽고 복사·로그 출력하지 않는다.

## 전략과 체결

기존 전략을 그대로 적용했다. Momentum은 종가>60봉 평균일 때 목표95%, 아니면0. Mean Reversion은20봉 z-score<−1에서95% 진입, z≥0에서0으로 청산. BuyHold는95% 비중 유지·재조정이다. 종목별 계좌 초기자금은 각각 $100,000이며, 하나의 분산 포트폴리오가 아니다.

공통 마지막252거래일은 **2025-11-24~2026-11-24**, 이전102거래일은 지표 warmup에 쓴다. 파라미터를 결과에 맞춰 튜닝하지 않았다. 신호는 이전 정규장 close+가정 처리 지연1분 이후 사용하고 다음 세션 첫 관측 IEX1분봉 open으로 체결을 모형화한다. 원래 과거 수집 지연을 측정한 실시간 운영 기록이 아니다.

편도 비용:commission1bp +slippage2bp +half spread1bp +impact5bp×sqrt(주문수량/이전 정규장 거래량). 이전 정규장 IEX 거래량1% 참여 한도와 실제 보유 현금에 따른 부분체결을 적용한다. 분할 당일 이전 거래량과 수량의 단위를 함께 바꾼다. 실제 opening-minute/order-book 수용량을 검증한 체결 모형은 아니다.

거래 가격과 NAV는 raw 가격이다. 신호용 close는 **해당 시점까지 발생한 split 누적 배수**를 곱해 연결하므로 이후 split이 과거 신호를 바꾸지 않는다. 배당은 ex-date 개장 직전 보유 수량에 권리가 발생하고 미수금으로 NAV에 포함한다. 현금 사용 가능 시점은 보수적으로 **payable date 다음 XNYS 세션 개장**을 가정한다. 정확한 개인 계좌 입금 시각은 알 수 없다. 실제 이번 구간에서는 배당 처리를 적용했고 split은 별도 수량·시그널·거래량 테스트로 검증했다.

정수 수량·Decimal 현금/배당0.0001 USD 반올림, 공매도/차입/펀딩 없음, 현금 이자·세금·기타 브로커별 제비용 미반영. 미청산 포지션과 미수금은 마지막 종가로 평가한다. 승률/Profit Factor는 청산 매도 체결 기준이며 완전한 왕복 거래 수익률과 다를 수 있다.

## 결과

아래는 전체252세션 누적 수익률이며 단일 거래 수익률이 아니다.

| 종목 | Momentum 비용 전 | 비용 후 | Mean Reversion 비용 전 | 비용 후 | 95% BuyHold 비용 후 |
|---|---:|---:|---:|---:|---:|
| AAPL | +11.78% | +11.07% | +4.60% | +4.22% | +29.39% |
| MSFT | +0.06% | -0.11% | +4.47% | +3.71% | +5.28% |
| NVDA | -14.50% | -15.43% | -1.37% | -2.10% | -12.17% |
| TSLA | -26.16% | -27.19% | +25.77% | +24.63% | -3.66% |
| SPY | +5.01% | +4.07% | +7.30% | +6.24% | +9.13% |

| 종목 | Momentum 최대 낙폭 | Mean Reversion 최대 낙폭 | BuyHold 최대 낙폭 |
|---|---:|---:|---:|
| AAPL | -13.05% | -11.29% | -13.10% |
| MSFT | -12.89% | -16.21% | -26.68% |
| NVDA | -23.10% | -41.61% | -45.61% |
| TSLA | -40.74% | -22.67% | -37.34% |
| SPY | -7.51% | -9.39% | -10.75% |

Momentum은5종목 모두 같은 종목 BuyHold보다 낮았다. Mean Reversion은NVDA/TSLA에서 상대적으로 높았지만 NVDA는 손실이며 낙폭도 컸다. 표본 기간·현재 선택 종목 묶음에서의 결과로 일관된 전략 우위나 다음 기간 수익성을 주장하지 않는다.

전체15개 성과, 비용 전후, Sharpe·CAGR·낙폭·회전율·체결 수·배당 현금/미수금은 [real_equity_results.json](real_equity_results.json)에 있다. 체결·곡선·검사 CSV는 해당 JSON의 로컬 result_directory에 있다. 코드·설정·입력 해시와 패키지 버전을 함께 기록한다.

## 노트북과 재현

[QuantCore_Real_Stocks_Backtest.ipynb](../notebooks/QuantCore_Real_Stocks_Backtest.ipynb)는 기본 AAPL/Momentum으로 표·5개 그래프와15개 비교를 제공한다. 종목/전략 위젯으로 상세 결과를 바꿀 수 있다. `SHOW_RAW_DATA=True`는 개인 로컬 분석용 가격 표시이며 공개 출력 기본값은False다. 입력이 없으면 합성 자료로 대체하지 않고 중단한다.

```bash
make real-setup
.venv/bin/python scripts/collect_real_equities.py --env-file /authorized/path/.env
make real-backtest
make real-notebook-check
```

이미 수집한 동결본이 있으면 수집 명령 없이 재실행한다. 새 환경에서 자신의 사용 권한이 있는 Alpaca 키가 필요하다. 키 없는 clone에도 저장된 표와 그래프는 보이지만 실제 재계산을 위해 원시 동결본을 공개 배포하지 않는다.

현금·보유 수량·NAV 대사, 신호 이용 시각<체결 시각, 마지막10일 가격 변경에 대한 과거 체결 불변성을15개 비교 전부 검사했다. calendar/DST/휴장/조기 폐장·배당 권리/현금·분할 단위·GET 경로 제한·부분 수집 실패·해시 훼손 검사는 테스트에 포함한다. 최신 테스트 수와 두 커널 실행 기록은 README/실행 검증 JSON을 참조한다.

## 적용 한계와 출처

IEX는 단일 시장이며 consolidated SIP가 아니다. 최신 보관본의 정정/생존 편향, 현재 종목 선정 편향, 가정 체결·비용·현금 지급 시각이 남는다. 장외 전략·상폐 universe·실주문 성과·뉴스/SEC/ML 추가 효과는 이 실험에서 검증하지 않았다. 현재 실제 API/웹 모드는 같은 검증 시세를 조회하며, 기본 keyless Compose의 합성 데모와 구분한다. 노트북의 과거 동결본은 보존한다.

공식 문서: [Historical bars](https://docs.alpaca.markets/us/reference/stockbars), [Market Data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq), [Corporate actions](https://docs.alpaca.markets/us/reference/corporateactions-1), [Daily processes](https://docs.alpaca.markets/us/docs/daily-processes-and-reconcilations), [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars).
