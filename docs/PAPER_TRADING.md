# Alpaca paper trading · 2026-11-25

사용자의 명시적인 후속 요청으로 기존 연결을 모의투자에 확장했다. `quantcore/paper/client.py`, `runner.py`, `scripts/run_paper_trading.py`를 추가했다. 기존 전략·과거 백테스트·합성 대시보드는 유지했다. 원격 주문은 Alpaca의 모의투자 시스템에 접수되며 실제 거래소로 전송되는 실거래 주문이 아니다.

현재 전략 예산은 사용자의 후속 승인으로 **$100,000**이며, 종목당 $20,000 슬롯의95%를 목표로 한다. 최초의 $5,000/2주씩 주문 기록은 아래에 보존했고, 예산 변경 후에는 기존 주문을 취소하고 AAPL53주·TSLA48주를 접수했다. 현재 상태와 예산 변경 절차는 [PAPER_AUTOMATION.md](PAPER_AUTOMATION.md)를 참조한다.

## 실제 실행 상태

11:17 KST에 ACTIVE USD paper 계정의 빈 보유/주문 상태를 확인한 뒤 AAPL2주·TSLA2주를 매수 접수했다. 두 주문은 `accepted`, 체결 수량은 각각0주였다. 11월24일 완료 정규장 자료의 Momentum 신호이며, MSFT/NVDA/SPY는 현금 유지다. 다음 정규장은 **2026-11-25 23:30 KST**다. 지정가 조건에 따라 미체결/부분 체결/만료될 수 있다. 체결 수익률이나 성공적인 전략 성과를 보고한 것이 아니다.

최초 실행은 일회성이었고, 후속 요청으로5분 간격 자동 운영 경로를 추가했다. 현재 실행 상태와 시작/중지는 [PAPER_AUTOMATION.md](PAPER_AUTOMATION.md)를 참조한다. 접수 주문은 Alpaca에 남아 정규장에 처리되고 `status` 또는 자동 주기가 실제 상태를 갱신한다. 이 문서와 [paper_trading_results.json](paper_trading_results.json)은 최초 확인 시점의 기록이며 자동 갱신되는 계좌 화면이 아니다. Alpaca 웹 대시보드의 Paper 모드에서도 주문을 확인할 수 있다.

## 주문 규칙

- Momentum: 기존60봉 평균보다 신호 종가가 높으면 목표95%, 아니면0. Mean Reversion도 선택 가능하지만 동일 계정 원장의 전략/예산을 중간에 바꾸면 중단한다. 이번 실제 실행은 Momentum이다.
- 현재 전략 예산 상한 $100,000, 5종목 슬롯당 $20,000. 95%는 각 슬롯에 적용하며 활성 종목이2개면 전체 예산을 전액 투자하지 않는다. 최초 $5,000 실행의 최대 매수 대금은 $1,493.20, 변경 후 두 주문의 최대 지정가 대금은 $37,625.75다. 정수 수량과 가용 현금 제한을 적용한다.
- 매수 지정가는 최근 완료 종가의101%를 센트 단위로 올림, 매도는99%를 내림한다. 매수 수량은 슬롯 목표액/매수 지정가를 내림한다. 매도 수량은 실제 소유 수량 이내다. `type=limit`, `time_in_force=day`, `extended_hours=false`만 허용한다. 백테스트의 다음 시가 체결과는 다른 제한 주문 정책이다.
- IEX 동결본의 해시·출처·완료 세션·가용 시각·60봉 이상 이력을 검사한다. API 시계와 XNYS의 다음 개장을 대조한다. 정규장 개장5분 이후에는 따라잡기 주문을 내지 않는다. 후속 거래일에는 시세 수집기를 다시 실행해 최신 완료 거래일 자료를 준비해야 한다. 이미 알려진 다음 개장 전 split이 있으면 중단하며, 이후 새로 공지된 기업행사를 완전히 감시하는 서비스는 아니다.
- 현금과 buying power의 작은 값을 사용해 차입을 피한다. 예정 매수 지정가 대금, 미체결 잔량 예약, 기존 보유 평가액을 합해 예산을 검사한다. 미체결 매도 대금을 가용 현금으로 가정하지 않는다. 예산/현금이 부족한 신규 매수는 정수 수량으로 줄이거나 다음 평가까지 미루며, 기존 보유분의 매도는 계속 처리한다. 가격 상승으로 보유 평가액이 예산을 넘을 수 있다.
- 기존 포지션은 원장의 실제 filled_qty와 일치해야 한다. 외부 주문/포지션이나 기업행사로 원장이 어긋나면 중단한다. 사용자 보유 종목을 임의로 청산하지 않는다.

## 실행과 중지

`make real-setup`으로 기존 realdata 의존성을 설치한다. 키는 환경 변수 또는 명시적인 환경 파일에서 읽는다. `ALPACA_PAPER_API_KEY`/`ALPACA_PAPER_SECRET_KEY`를 지정할 수 있고, 없으면 기존 `ALPACA_API_KEY`/`ALPACA_SECRET_KEY` 또는 `APCA_API_KEY_ID`/`APCA_API_SECRET_KEY`를 사용한다. 실제 값은 저장소에 넣지 않는다.

```bash
.venv/bin/python scripts/run_paper_trading.py plan --env-file /authorized/path/.env
.venv/bin/python scripts/run_paper_trading.py run --env-file /authorized/path/.env
.venv/bin/python scripts/run_paper_trading.py status --env-file /authorized/path/.env
```

`plan`은 주문 없이 검사·계획만 저장한다. `run`은 검사 후 모의 주문을 제출한다. 같은 계정/전략/거래일/종목에 동일한 client_order_id를 사용하므로 반복 실행으로 주문을 추가하지 않는다. 실제 반복 실행에서도 추가 주문0건·POST0건을 확인했다. 취소/거절/만료 후에도 같은 날 임의의 재시도 ID를 만들지 않는다.

```bash
# 다음 신규 주문을 차단. 이미 접수된 주문은 그대로 남는다.
touch artifacts/paper_trading/STOP
# 프로그램 원장에 속한 미체결 모의 주문만 취소
.venv/bin/python scripts/run_paper_trading.py cancel --env-file /authorized/path/.env
```

원장과 계정이 일치하는지 확인한 뒤 `STOP`을 제거하면 신규 주문이 다시 허용된다. 계정 전체 주문 취소, 포지션 전체 청산, 실거래 모드는 제공하지 않는다. 웹은 실제 Alpaca 시세 분석 모드도 지원한다. paper 계좌 원장/주문 UI는 제공하지 않으며 status CLI로 확인한다.

## 중복·장애 처리와 보관

로컬 프로세스 파일 잠금과 SQLite 영속 intent를 사용한다. POST 직전에 payload를 커밋하고, 같은 ID가 broker에 있는지 먼저 조회한다. 네트워크 타임아웃/서버 오류/해석 불가능한 응답은 client_order_id로 조회해 결과를 복구한다. 조회로 확인되지 않으면 `unknown`으로 중단하고 자동으로 POST를 재시도하지 않는다. crash가 POST 전에 일어난 경우도 수동 대사 전에는 보내지 않는다. 새 디렉터리에서 별도 프로세스를 실행해도 broker의 동일 ID가 중복을 막지만, 다른 전략과 병렬 운영하는 계좌 구성은 지원하지 않는다.

`artifacts/paper_trading/`는 Git에서 제외한다. `journal.sqlite3`, `initial_submission.json`, `latest_plan.json`, `latest_run.json`, `latest_status.json`, `duplicate_check.json`은 로컬 운영 기록이다. 원장에는 비밀 키를 저장하지 않는다. 계정 ID·주문 ID·원문 응답은 공개 요약에서 제외했다. 불확실한 주문의 원장을 지우거나 `rejected_locally`로 바꾸어 재전송하지 말고 broker의 실제 주문 상태부터 확인해야 한다.

## 검증과 해석

최초 실행의 전체 테스트는115개 통과,19.51초, 문장 커버리지96.25%(`quantcore`+`apps/api`), 기존 TestClient 경고1개였다. 자동 운영 추가 후에는133개 통과,25.13초, 커버리지96.25%다. paper 관련51개 사례는 계획만 실행, 실제 클라이언트 MockTransport의 제출/조회/취소, 중복 실행, 부분/완전 체결 대사, 타임아웃의 접수/미접수, 현금 부족/차단 계정/타인 포지션/타인 주문, 오래된/미래 자료, split, 개장 시간, 한도, 파일 잠금, broker payload 불일치, 실계좌 URL/redirect 차단과 자동 실행·증분 수집을 확인했다. Ruff가 통과했다. 웹 소스 변경이 없어 이번 프런트엔드 빌드/브라우저 검사는 다시 실행하지 않았다.

예산 변경 후 최신 검사는139개 통과,29.66초, 문장 커버리지96.21%다. 추가6개 사례에서 예산 revision/이력 보존, 취소·부분 체결 경합, 취소 미확정, 재제출 실패 시 중지, 가용 현금 제한과 타인 주문/상한 보호를 검사했다.

실제 paper API로 계정 조회·자산 거래 가능 여부·주문 제출·상태 조회·반복 실행을 확인했다. 최초에는 취소를 테스트로만 검사했고, 후속 예산 변경 때 자체 주문2건의 실제 취소 확정과 새 주문2건 접수를 확인했다. 아직 정규장 체결과 연속 운용 성과는 확인하지 못했다. Alpaca paper의 호가 기반 모의 체결은 실제 시장의 충격·지연 슬리피지·대기열·배당 등을 완전히 재현하지 않는다.

공식 문서: [Paper trading](https://docs.alpaca.markets/us/docs/paper-trading), [Create an order](https://docs.alpaca.markets/us/reference/postorder), [Placing orders](https://docs.alpaca.markets/us/docs/orders-at-alpaca), [Client order ID 조회](https://docs.alpaca.markets/us/reference/getorderbyclientorderid).
