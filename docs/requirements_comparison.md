# 요구사항 대조표

**기업 분류·기업행사/기간 분리(2026-11-25):** SEC SIC 기반 현재 위험 그룹·SPY ETF 식별, 공식 기업행사 수집/분할 원장/배당 권리·입금/종목변경 대사와 안전 중단, 사전 고정 규칙의 순차 검증/126일 연속 평가/비용 스트레스를 추가했다. 새 티커 자동 이관·단주 정산·과거 분할 포트폴리오 재현·미관측 외부 검증은 완료로 표시하지 않는다. [범위](REFERENCE_AND_CORPORATE.md) · [정량 검증](WALK_FORWARD_VALIDATION.md).

**실제 paper 실적 추적(2026-11-25):** 계좌 평가액/활동 GET 자동 수집, 실제 체결 평균원가 손익·체결률·주문 근거·신선도, 모의투자 현황 탭과 읽기 전용 API를 추가했다. 현재0체결로 다일간 수익성은 미검증이다. [정의·검증](PAPER_PERFORMANCE.md).

**전체 계좌·주문 리스크 추가(2026-11-25):** paper와 공용 5슬롯·지정가·비용 정책의 실제 분봉 replay, 독립 일일 손실/낙폭/변동성/유동성/집중도 필터, 자체 대기 매수 취소·로컬 알림·노트북·읽기 전용 API/UI를 추가했다. [범위·결과·한계](PORTFOLIO_PAPER_PARITY.md).

**2026-11-25 추가:** Alpaca 실제 미국 종목5개의 시세 수집·XNYS 거래일·배당 미수금/지급·실제 종목 백테스트와 별도 노트북을 구현했다. 최신 범위와 정량 결과는 [REAL_STOCK_BACKTEST.md](REAL_STOCK_BACKTEST.md)를 참조한다. 아래 표는 초기MVP 대조 기록이다.

**실제 API 통합 추가:** 웹/API에 Alpaca 모드를 연결했다. 가격·기술·백테스트·포트폴리오/리스크·통계·Ridge 검증은 실제 시세를 사용하고, 재무/멀티팩터는 실제 입력 없음으로 반환한다.156개 테스트, 실제 UI10개·데모 UI4개 시나리오를 검증했다. 자동 paper는 별도 경로로 유지한다. [검증 기록](actual_api_validation.json).

2026-11-24. 두 첨부 텍스트는 byte diff 결과 동일했다. 요구사항 마지막 절의 **실행 가능한 MVP 우선** 기준을 적용한다. 전체 기관급 플랫폼의 모든 Phase가 완료됐다는 의미가 아니다.

| 요구 구역 | 시작 시 상태 | 이번 개발 / 완료 범위 | 남은 범위 |
|---|---|---|---|
| 2 공개 저장소 조사 | 원본 조사 파일만 존재 | 23개 archive 조사·근거 경로/해시·설계 적용 기록 | 전체 소스/테스트 실행은 하지 않음; 일부 repo는 README만 공개 |
| 3–4 기반/스택 | Python 분석 모듈 일부 | 모듈형 단일 API, 필요한 의존성 선택·lock | 분산 서비스/저수준 확장 미도입 |
| 5 시장 데이터 | DemoProvider/저장 코드 | 합성 6종목 OHLCV, 비동기 수집·재시도·검증·중복 방지·Parquet/DuckDB; 별도 실제 Alpaca IEX5종목·XNYS calendar·동결본 | tick/order book, 추가 시장·전체 과거 투자 가능 universe |
| 6 증분 계산 | 미검증 Graph | DAG/배치/dirty/cache/version/구독/순환 검사, 전체 재계산 동등성·rolling 통계 | 동적 대형 DAG 스케줄러·분산 계산 |
| 7 재무 | 계산 함수 | 17개 비율·금액 항목, 시점/기간/공식/산업 제한, 수정 공시 버전 분리 | 실제 XBRL/분기·TTM, CCC/Z/F/M score |
| 8 가치평가 | DCF 함수 | FCFF DCF·민감도·명시 가정·Monte Carlo·UI 입력 | WACC 산출/FCFE/DDM/잔여이익/상대·역DCF/SOTP |
| 9 팩터 | 점수 함수 | 6계열 점수, winsorize/z-score/rank/섹터 중립/사용자 가중치/Rank IC | 전체 세부 팩터·시총중립·decay/ICIR/귀속 |
| 10 기술 분석 | 지표 함수 | 15계열 지표·거래량/변동성/돌파, 기준값·미래 불변성 검사 | true tick VWAP·다중 주기·breadth. 일봉 VWAP는 proxy |
| 11 통계 | 빈 모듈 | 기술 통계·상관/공분산·OLS/Huber/PCA·block bootstrap·BH 보정 | ADF/KPSS/cointegration/GARCH/ARIMA/HMM/Granger |
| 12 ML | 미검증 검증 함수 | Ridge/평균 baseline·purge/embargo·학습 전용 scaler·OOS 비교 | deep models/XGB/LGBM/Optuna/SHAP/MLflow/drift |
| 13–14 전략/백테스트 | 미검증 함수 | Momentum/Mean Reversion/BuyHold, 다음 봉 체결·비용·부분체결·수량/현금 보존·배당/분할/상폐 handler·성과 지표 | 공매도/차입/펀딩·상폐 universe/호가 기반 영향 |
| 15 포트폴리오 | optimizer 함수 | Equal/MinVar/RiskParity·40% cap·수렴/불가능 제약 검사·위험 기여 UI | HRP/BL/CVaR/효율적 경계·섹터/국가/통화/회전 제약 |
| 16 리스크/파생 | 계산 함수 | Historical/Normal/MC VaR·ES·낙폭·상관·집중·가상 스트레스·BS Greeks/IV | 실제 2008/2020/2022 스트레스·곡면/스큐·금리/FX exposure |
| 17 거시 | 빈 모듈 | 사용자 제공 release/vintage의 시점 선택과 미래 수정 차단 | FRED/ALFRED 실제 수집·일정·surprise·경기 모델 |
| 18 AI assistant | 없음 | Python 계산 근거 보고서 API, LLM 꺼짐 명시 | 실제 LLM/RAG/공시·뉴스 수집·요약 |
| 19 대시보드 | 없음 | Next/React/ECharts·8개 작동 화면·종목 선택·가중치/DCF/전략/최적화·WS·모바일·한영·단축키 | 19페이지 전체·KRW환산·사용자 위젯 배치 |
| 20–21 구조/보안 | 일부 폴더 | 의존 방향·입력 검증·parameter SQL·선택형 API bearer·단일 연구자 역할·rate limit·audit·backup | 다중 사용자 RBAC/SSO/TLS gateway·운영 복구 훈련 |
| 22 성능 | 없음 | p50/95/99/99.9, DAG 비교·수집/DB/API·CPU/RSS·캐시/queue/WS send 측정 | 운영 부하/네트워크 RTT·Prometheus/Grafana/OTel |
| 23 검증 | 테스트 없음 | 단위/통합/속성/회귀/금융/누출 검사 + 실제 브라우저 시나리오 | 실제 시장·대규모 운영 검증 |
| 24 안전 | 기존에는 연결 코드 없음 | 기본 Research/Demo, 별도 승인된 Alpaca paper CLI·예산/현금/중복/원장 검사·실제 모의 주문2건 접수 | 체결 이후 forward 성과·반복 운영 검증, 실거래 미구현 |
| 25–27 실행/문서 | 계획 1개 | 실행 명령·Compose·CI 구성·실측 JSON·README·필수 문서 | 알려진 미구현 항목은 별도 추적 |

테스트/빌드/브라우저/컨테이너 실행 결과는 README와 `progress.md`의 최종 기록을 기준으로 한다. “구현”과 “환경에서 실제 실행 검증”을 구분한다.
