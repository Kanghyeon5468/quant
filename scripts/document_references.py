"""Summarize inspected public evidence, explicitly marking unobserved details."""
import json
import re
from pathlib import Path

DESCRIPTIONS = {
 'base': ('이식 가능한 OCaml 표준 라이브러리', '명시적 인터페이스와 작은 범용 모듈', 'Map/Hashtbl/Result 등 표준 자료형', '입력 → 타입별 순수 연산 → 결과', 'core 계약과 계산 엔진을 I/O에서 분리'),
 'core': ('Base를 확장한 표준 라이브러리', 'Base 위 확장, Stable/bin_io 인터페이스', '비교자 기반 Map과 안정화된 타입', 'Base 연산 → Core 확장 API/직렬화', '이벤트·데이터 버전과 직렬화 계약 명시'),
 'async': ('비동기 프로그래밍 라이브러리', 'Async_kernel/Unix/RPC 층 분리', 'Deferred와 비동기 reader/writer', '외부 I/O 완료 → Deferred 연결 → 후속 연산', 'asyncio provider와 bounded queue로 대응'),
 'incremental': ('입력 변화에 따른 증분 계산', 'DAG 노드·가변 입력·stabilization', '노드/의존 관계/시계 상태', '변경 → dirty 전파 → 안정화 → 관측', 'Graph 배치 무효화·버전·전체 재계산 동등성'),
 'bin_prot': ('타입 안전한 바이너리 직렬화', 'size/read/write 및 타입 클래스 분리', 'Bigstring/버퍼 위치와 스키마', '크기 계산 → 버퍼 기록 → 검증된 읽기', 'Pydantic 계약·Parquet 스키마와 해시'),
 'torch': ('PyTorch C++ API의 OCaml 바인딩', '자동 생성 바인딩·tensor/layer 모듈', 'Tensor/Var_store', 'tensor 입력 → 연산/자동미분 → 결과', 'ML과 데이터 계약 분리; 현재는 sklearn baseline만 도입'),
 'hardcaml': ('하드웨어 회로 설계·시뮬레이션·RTL 생성', 'Signal과 회로 변환/시뮬레이터 분리', 'Signal/회로/포트/RAM', '설계 → 시뮬레이션 → RTL 출력', '결정론적 상태 전이 검증 철학; FPGA는 미도입'),
 'magic-trace': ('프로그램 실행 추적과 분석 도구', '수집/추적 분석/시각화 도구 구성', '추적 이벤트·압축된 실행 정보', '실행 추적 → 분석 → 시각화', '실측 후 최적화; perf_counter 지연 분포 구현'),
 'core_bench': ('OCaml 마이크로벤치마크 도구', '측정과 분석 및 runner 분리', '측정 표본/분석 결과', '작업 반복 → 표본 수집 → 비교', '워밍업·분포·환경을 남기는 DAG/API 벤치마크'),
 'memtrace': ('OCaml Memprof 메모리 추적', 'streaming 기록과 viewer 분석 분리', '할당/수거 이벤트와 공유 writer', '할당 표본 → compact trace → 메모리 분석', 'Python peak RSS 측정; 누수 분석은 후속'),
 'bonsai': ('반응형 OCaml UI 라이브러리', '함수형 상태 머신과 증분 렌더링', '상태/Effect/Incr.Var', '상태 갱신 → 의존 계산 → UI 효과', 'React 상태·WebSocket snapshot·계산과 표시 분리'),
 'rpc_parallel': ('타입 안전한 프로세스 worker RPC', 'worker 상태와 connection 상태 구분', 'worker ID/연결/RPC 함수', 'spawn → typed RPC → worker 결과', 'fault isolation 참고; 분산 프로세스 미도입'),
 'parallel': ('OxCaml Parallelism이라는 README만 확인', '실제 구현 파일 없음', '미확인', '미확인', '구현/라이선스 확인 전 도입하지 않음'),
 'bignum': ('임의 정밀도 유리수/큰 수 연산', 'Zarith 기반 수치 타입', '정수·유리수/큰 정수', '정밀 값 → 산술 → 문자열/표현', '금전 원장 Decimal과 float 통계의 경계 설정'),
 'bigdecimal': ('고정밀 십진수 표현', 'mantissa×10^exponent 표현', 'Bigint mantissa와 정수 exponent', '십진 입력 → 정밀 연산 → 십진 출력', 'Decimal 원장·명시적 반올림·정수 수량'),
 'base_quickcheck': ('무작위 속성 기반 검사', 'generator/observer/shrinker/test 분리', '생성기·축소기·설정 seed', '생성 → 속성 실행 → 실패 사례 축소', 'Hypothesis 증분 일치/옵션 parity 속성 검사'),
 'ppx_jane': ('표준 PPX 전처리기 묶음', 'opam 의존성으로 여러 PPX 조합', 'OCaml AST 변환 구성', '타입/구문 → 전처리 → 생성 코드', '자동 계약과 회귀 출력 검사 철학; PPX 자체 사용 안함'),
 'async_rpc_kernel': ('이식 가능한 비동기 RPC 프로토콜', 'RPC 인터페이스와 서버 구현 분리', 'Rpc/State_rpc/Pipe_rpc/transport', '요청 → 프로토콜 해석 → 구현 → 응답', 'API 응답 스키마·일회용 WS ticket'),
 'ocaml_simd': ('OxCaml SIMD intrinsics라는 README만 확인', '실제 구현 파일 없음', '미확인', '미확인', '프로파일링 증거 없으므로 SIMD 확장 미도입'),
 'ocaml_intrinsics': ('하드웨어 명령의 OCaml 인터페이스', 'intrinsic/C stub fallback', '정수·CRC/명령 wrapper', '호출 → 하드웨어 또는 fallback → 결과', '측정 전 intrinsics 사용하지 않음'),
 'postgres_async': ('PostgreSQL wire protocol 클라이언트', 'Async 기반 질의/파라미터/COPY 지원', '연결·query·SSL mode', '파라미터 질의 → 프로토콜 I/O → 결과', '파라미터 SQL·저장소 추상화, MVP는 SQLite'),
 'redis-async': ('Async 기반 Redis RESP3 클라이언트', 'typed serializer와 연결/역할 모듈', '인증/role/연결/typed payload', '명령 → RESP3 → typed 응답', '캐시 경계·실패 격리; Redis 의존성 보류'),
 'incr_map': ('Map 연산의 증분 계산', 'Incremental과 Map diff 조합', 'Map/symmetric diff/증분 노드', 'map 변경분 → 연산 → 새 증분 결과', '바뀐 종목의 DAG 가지를 갱신'),
}


def main():
    evidence = json.loads(Path('docs/reference_evidence.json').read_text())
    lines = ['# Jane Street 공개 저장소 조사', '', '조사일: 2026-11-24. 공개 master archive의 일부 파일을 읽었다. OCaml 코드를 실행하거나 제품 코드에 복사하지 않았다. 전체 코드 감사나 Jane Street 내부 거래 시스템 분석이 아니다.', '',
        '조회 파일·크기·SHA-256·archive SHA-256은 [reference_evidence.json](reference_evidence.json)에 있다. master는 변경 가능하므로 해시로 이번 관측을 구분한다. 임시 조사 복사본은 `/private/tmp/quantcore-references/`에 있다.', '',
        '아래 적용 항목은 공개 패턴을 Python MVP로 옮긴 설계 판단이다. 저장소에서 직접 확인하지 못한 메모리/동시성/테스트 세부사항은 미확인으로 표시한다.', '']
    for item in evidence:
        name = item['repository']
        text = (Path('/private/tmp/quantcore-references')/(name+'.review.txt')).read_text() if item['status'] == 'retrieved' else ''
        parts = text.split('FILE ')[1:]
        source = '\n'.join(p for p in parts if p.split('\n')[0].endswith(('.ml', '.mli')))
        dependencies = []
        for part in parts:
            if part.split('\n')[0].endswith('.opam'):
                dependency_block = part.split('depends:', 1)[-1].split('available:', 1)[0]
                dependencies.extend(re.findall(r'^\s*"([a-z][a-z0-9_-]+)"', dependency_block, re.M))
        license_name = 'MIT (LICENSE/opam 확인)' if 'The MIT License' in text else '미확인: 라이선스 파일을 확보하지 못해 코드 도입하지 않음'
        core, architecture, structure, flow, application = DESCRIPTIONS[name]
        tests = [f['path'] for f in item.get('files', []) if any(x in f['path'] for x in ('/test', 'test/', '/bench', 'bench/')) and f['path'].endswith(('.ml', '.mli'))]
        memory = '별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음'
        if name == 'torch':
            memory = 'README에서 deterministic refcounting 명시; Python MVP가 이를 재현한다고 주장하지 않음'
        if name == 'bigdecimal':
            memory = 'Bigint mantissa/exponent 표현 확인; 할당/GC 최적화 효과는 미측정'
        if name == 'memtrace':
            memory = 'Memprof 할당/수거 표본 기록과 shared writer lock 확인; 자체 메모리 효율은 미측정'
        concurrency = '라이브러리의 병렬 실행 보장은 선택 자료에서 미확인'
        if name in ('async', 'async_rpc_kernel', 'postgres_async', 'redis-async'):
            concurrency = 'Async/Deferred 기반 비동기 I/O 확인; CPU 병렬성과 구분'
        if name == 'rpc_parallel':
            concurrency = 'worker spawn과 RPC 함수/connection 상태 분리 확인; 실제 실행 안함'
        if name in ('parallel', 'ocaml_simd'):
            concurrency = 'README의 명칭 이외 구현과 동기화 세부사항 미확인'
        errors = [token for token in ('Or_error', 'Result', 'raise', 'exception') if token in source]
        error_note = ', '.join(errors)+' 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음' if errors else '선택 소스에서 구체 오류 정책 미확인'
        rows = [('핵심 기능', core), ('아키텍처·의존성', architecture+'; opam: '+(', '.join(dict.fromkeys(dependencies)) or '미확인')),
            ('자료구조', structure), ('처리 흐름', flow), ('메모리', memory), ('동시성·병렬', concurrency),
            ('오류', error_note), ('성능', '공개 설계의 선택적/타입별 계산 원칙 참고. '+('도구/trace/반복 표본 분석을 제공; ' if name in ('core_bench', 'magic-trace', 'memtrace') else '')+'QuantCore 속도 향상은 별도 실제 벤치마크로만 판단'),
            ('테스트·검증', ('읽은 테스트/벤치: '+', '.join(tests) if tests else '선택 파일에 독립 테스트/벤치 없음; inline/다른 저장소 검증을 추정하지 않음')+'; 원본 OCaml 테스트 미실행'),
            ('QuantCore 적용', application)]
        lines += [f"## [{name}]({item['url']})", '', f'라이선스: {license_name}.', '', '| 조사 항목 | 확인 / 적용 판단 |', '|---|---|']
        lines += [f'| {key} | {value} |' for key, value in rows]
        files = item.get('files', [])
        lines += ['', '읽은 파일: '+', '.join(f"[{f['path']}]({item['url']}/blob/master/{f['path']})" for f in files)+'.', '']
    lines += ['## 라이선스와 추정의 경계', '', '확인된 라이선스는 해당 저장소 상위 LICENSE와 opam 기준이다. 코드 복사·바인딩 도입 없이 개념을 참고해 새 Python 코드를 작성했다. `parallel`, `ocaml_simd`는 이번 archive가 README 1개뿐이어서 소스·테스트·라이선스를 확인하지 못했다. 공개 문서가 내부 사용을 언급하더라도 내부 전략·수익·인프라 세부사항으로 확대 추측하지 않는다.']
    Path('docs/reference_analysis.md').write_text('\n'.join(lines)+'\n')


if __name__ == '__main__':
    main()
