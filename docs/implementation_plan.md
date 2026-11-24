# 구현 계획 · 2026-11-24

## Phase 0: 조사
- 신규 Git 저장소: 기존 코드 없음, origin Kanghyeon5468/quant, 로컬 main.
- 이전 stock 프로젝트와 독립 구현. 기존 API 키·데이터·실거래 모듈을 가져오지 않는다.
- Jane Street 23개 공개 저장소의 README, 소스, 테스트, opam 의존성, 라이선스 조사 기록.

## 실행 가능한 MVP 범위
1. Python 3.12/FastAPI/Pydantic, SQLite/SQLAlchemy, Parquet/DuckDB 저장·조회.
2. UTC/가용 시각/데이터 출처/통화/단위 검증, 재시도·속도 제한·비동기 demo 수집.
3. 이벤트 버스, 배치 무효화 DAG, 버전/캐시/구독, rolling 통계.
4. 기본 재무 비율과 근거, DCF/민감도, 기술 지표, 횡단면 팩터.
5. momentum/mean reversion 공통 전략, 다음 봉 시가 체결·Decimal 원장·비용·유동성 제한·기업행사.
6. 포트폴리오 최적화·리스크·가상 스트레스·Black-Scholes, 간단한 Ridge/Dummy 시계열 검증.
7. Next.js/React/TypeScript 대시보드, ECharts, 한국어/영어, WebSocket 갱신.
8. 단위/통합/속성/회귀/E2E 검증, API·DAG 벤치마크, 실제 실행 결과 문서화.

## 의존성 선택
NumPy/Pandas/SciPy: 검증 가능한 수치 계산. SQLAlchemy/SQLite: 별도 서비스 없이 트랜잭션·유일성.
PyArrow: Parquet, DuckDB: 로컬 분석 조회. scikit-learn: 기본 모델 비교.
FastAPI/Uvicorn/Pydantic: API·WS·입력 계약. Next.js/React/ECharts: 실제 작동하는 분석 UI.
Pytest/Hypothesis/coverage/Ruff/Mypy/Playwright: 핵심 경로 검사.
Postgres/Timescale/Redis, Polars/Numba, PyTorch/대형 ML/LLM, 분산 서비스는 MVP 부하와 입력이 없어 도입 보류.

## 완료 기준
키 없이 bootstrap → 실제 저장 → API/UI 조회 → 2개 전략 결과 → 리스크 → 자동 테스트.
Docker Compose 구성을 제공하며 Docker daemon 사용 가능 여부와 실제 빌드 여부를 구분 기록한다.
데모 수익률은 합성 자료의 모의 성과로만 표시한다. 과거 프로젝트 실데이터 성과를 복사하지 않는다.
