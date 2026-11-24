# 요구사항 대조표

2026-11-24. 두 첨부 텍스트는 byte diff 결과 동일했다. 요구사항 마지막 절의 **실행 가능한 MVP 우선** 기준을 적용한다. 전체 기관급 플랫폼의 모든 Phase가 완료됐다는 의미가 아니다.

| 요구 구역 | 시작 시 상태 | 이번 개발 / 완료 범위 | 남은 범위 |
|---|---|---|---|
| 2 공개 저장소 조사 | 원본 조사 파일만 존재 | 23개 archive 조사·근거 경로/해시·설계 적용 기록 | 전체 소스/테스트 실행은 하지 않음; 일부 repo는 README만 공개 |
| 3–4 기반/스택 | Python 분석 모듈 일부 | 모듈형 단일 API, 필요한 의존성 선택·lock | 분산 서비스/저수준 확장 미도입 |
| 5 시장 데이터 | DemoProvider/저장 코드 | 합성 6종목 OHLCV, 비동기 수집·재시도·검증·중복 방지·Parquet/DuckDB | 실제 provider, tick/order book, 실제 거래소 calendar |
| 6 증분 계산 | 미검증 Graph | DAG/배치/dirty/cache/version/구독/순환 검사, 전체 재계산 동등성·rolling 통계 | 동적 대형 DAG 스케줄러·분산 계산 |
| 7 재무 | 계산 함수 | 17개 비율·금액 항목, 시점/기간/공식/산업 제한, 수정 공시 버전 분리 | 실제 XBRL/분기·TTM, CCC/Z/F/M score |
| 8 가치평가 | DCF 함수 | FCFF DCF·민감도·명시 가정·Monte Carlo·UI 입력 | WACC 산출/FCFE/DDM/잔여이익/상대·역DCF/SOTP |
| 9 팩터 | 점수 함수 | 6계열 점수, winsorize/z-score/rank/섹터 중립/사용자 가중치/Rank IC | 전체 세부 팩터·시총중립·decay/ICIR/귀속 |
| 10 기술 분석 | 지표 함수 | 15계열 지표·거래량/변동성/돌파, 기준값·미래 불변성 검사 | true tick VWAP·다중 주기·breadth. 일봉 VWAP는 proxy |
| 11 통계 | 빈 모듈 | 기술 통계·상관/공분산·OLS/Huber/PCA·block bootstrap·BH 보정 | ADF/KPSS/cointegration/GARCH/ARIMA/HMM/Granger |
| 12 ML | 미검증 검증 함수 | Ridge/평균 baseline·purge/embargo·학습 전용 scaler·OOS 비교 | deep models/XGB/LGBM/Optuna/SHAP/MLflow/drift |
| 13–14 전략/백테스트 | 미검증 함수 | Momentum/Mean Reversion/BuyHold, 다음 봉 체결·비용·부분체결·수량/현금 보존·배당/분할/상폐 handler·성과 지표 | 공매도/차입/펀딩·실제 시장 캘린더/상폐 universe/호가 기반 영향 |
| 15 포트폴리오 | optimizer 함수 | Equal/MinVar/RiskParity·40% cap·수렴/불가능 제약 검사·위험 기여 UI | HRP/BL/CVaR/효율적 경계·섹터/국가/통화/회전 제약 |
| 16 리스크/파생 | 계산 함수 | Historical/Normal/MC VaR·ES·낙폭·상관·집중·가상 스트레스·BS Greeks/IV | 실제 2008/2020/2022 스트레스·곡면/스큐·금리/FX exposure |
| 17 거시 | 빈 모듈 | 사용자 제공 release/vintage의 시점 선택과 미래 수정 차단 | FRED/ALFRED 실제 수집·일정·surprise·경기 모델 |
| 18 AI assistant | 없음 | Python 계산 근거 보고서 API, LLM 꺼짐 명시 | 실제 LLM/RAG/공시·뉴스 수집·요약 |
| 19 대시보드 | 없음 | Next/React/ECharts·8개 작동 화면·종목 선택·가중치/DCF/전략/최적화·WS·모바일·한영·단축키 | 19페이지 전체·KRW환산·사용자 위젯 배치 |
| 20–21 구조/보안 | 일부 폴더 | 의존 방향·입력 검증·parameter SQL·선택형 API bearer·단일 연구자 역할·rate limit·audit·backup | 다중 사용자 RBAC/SSO/TLS gateway·운영 복구 훈련 |
| 22 성능 | 없음 | p50/95/99/99.9, DAG 비교·수집/DB/API·CPU/RSS·캐시/queue/WS send 측정 | 운영 부하/네트워크 RTT·Prometheus/Grafana/OTel |
| 23 검증 | 테스트 없음 | 단위/통합/속성/회귀/금융/누출 검사 + 실제 브라우저 시나리오 | 실제 시장·대규모 운영 검증 |
| 24 안전 | 연결 코드 없음 | Research/Demo만 허용, 주문 API 없음 | Paper account/실거래는 별도 단계 |
| 25–27 실행/문서 | 계획 1개 | 실행 명령·Compose·CI 구성·실측 JSON·README·필수 문서 | 알려진 미구현 항목은 별도 추적 |

테스트/빌드/브라우저/컨테이너 실행 결과는 README와 `progress.md`의 최종 기록을 기준으로 한다. “구현”과 “환경에서 실제 실행 검증”을 구분한다.
