# Jane Street 공개 저장소 조사

조사일: 2026-11-24. 공개 master archive의 일부 파일을 읽었다. OCaml 코드를 실행하거나 제품 코드에 복사하지 않았다. 전체 코드 감사나 Jane Street 내부 거래 시스템 분석이 아니다.

조회 파일·크기·SHA-256·archive SHA-256은 [reference_evidence.json](reference_evidence.json)에 있다. master는 변경 가능하므로 해시로 이번 관측을 구분한다. 임시 조사 복사본은 `/private/tmp/quantcore-references/`에 있다.

아래 적용 항목은 공개 패턴을 Python MVP로 옮긴 설계 판단이다. 저장소에서 직접 확인하지 못한 메모리/동시성/테스트 세부사항은 미확인으로 표시한다.

## [base](https://github.com/janestreet/base)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | 이식 가능한 OCaml 표준 라이브러리 |
| 아키텍처·의존성 | 명시적 인터페이스와 작은 범용 모듈; opam: ocaml, base_stubs, basement, capsule0, nonempty_list_type, ocaml_intrinsics_kernel, ppx_array_base, ppx_base, ppxlib_jane, sexplib0, dune, ppxlib |
| 자료구조 | Map/Hashtbl/Result 등 표준 자료형 |
| 처리 흐름 | 입력 → 타입별 순수 연산 → 결과 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | 라이브러리의 병렬 실행 보장은 선택 자료에서 미확인 |
| 오류 | raise, exception 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 선택 파일에 독립 테스트/벤치 없음; inline/다른 저장소 검증을 추정하지 않음; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | core 계약과 계산 엔진을 I/O에서 분리 |

읽은 파일: [LICENSE.md](https://github.com/janestreet/base/blob/master/LICENSE.md), [README.org](https://github.com/janestreet/base/blob/master/README.org), [ppx/README.md](https://github.com/janestreet/base/blob/master/ppx/README.md), [composition_infix/README.md](https://github.com/janestreet/base/blob/master/composition_infix/README.md), [base.opam](https://github.com/janestreet/base/blob/master/base.opam), [src/t.ml](https://github.com/janestreet/base/blob/master/src/t.ml), [src/fn.ml](https://github.com/janestreet/base/blob/master/src/fn.ml), [src/exn.ml](https://github.com/janestreet/base/blob/master/src/exn.ml).

## [core](https://github.com/janestreet/core)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | Base를 확장한 표준 라이브러리 |
| 아키텍처·의존성 | Base 위 확장, Stable/bin_io 인터페이스; opam: ocaml, am_running_test, base, base_bigstring, base_quickcheck, basement, bin_prot, capsule, fieldslib, jane-street-headers, jst-config, parsexp, portable, ppx_assert, ppx_base, ppx_diff, ppx_expect, ppx_hash, ppx_inline_test, ppx_jane, ppx_optcomp, ppx_sexp_conv, ppx_sexp_message, ppx_stable_witness, sexplib, small_numbers_shim, splittable_random, stdio, string_dict, time_now, typerep, univ_map, variantslib, dune |
| 자료구조 | 비교자 기반 Map과 안정화된 타입 |
| 처리 흐름 | Base 연산 → Core 확장 API/직렬화 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | 라이브러리의 병렬 실행 보장은 선택 자료에서 미확인 |
| 오류 | Or_error, raise, exception 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: validate/test/test_validate.ml, validate/test/validate_test.ml; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | 이벤트·데이터 버전과 직렬화 계약 명시 |

읽은 파일: [LICENSE.md](https://github.com/janestreet/core/blob/master/LICENSE.md), [core/README.md](https://github.com/janestreet/core/blob/master/core/README.md), [base_for_tests/README.org](https://github.com/janestreet/core/blob/master/base_for_tests/README.org), [core.opam](https://github.com/janestreet/core/blob/master/core.opam), [core/src/t.ml](https://github.com/janestreet/core/blob/master/core/src/t.ml), [core/src/fn.ml](https://github.com/janestreet/core/blob/master/core/src/fn.ml), [core/src/gc.ml](https://github.com/janestreet/core/blob/master/core/src/gc.ml), [validate/test/test_validate.ml](https://github.com/janestreet/core/blob/master/validate/test/test_validate.ml), [validate/test/validate_test.ml](https://github.com/janestreet/core/blob/master/validate/test/validate_test.ml).

## [async](https://github.com/janestreet/async)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | 비동기 프로그래밍 라이브러리 |
| 아키텍처·의존성 | Async_kernel/Unix/RPC 층 분리; opam: ocaml, async_kernel, async_log, async_rpc_kernel, async_unix, core, core_kernel, core_unix, ppx_expect, ppx_jane, textutils, dune |
| 자료구조 | Deferred와 비동기 reader/writer |
| 처리 흐름 | 외부 I/O 완료 → Deferred 연결 → 후속 연산 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | Async/Deferred 기반 비동기 I/O 확인; CPU 병렬성과 구분 |
| 오류 | Or_error, raise 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: bench/tco.ml, bench/loop.ml; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | asyncio provider와 bounded queue로 대응 |

읽은 파일: [README.md](https://github.com/janestreet/async/blob/master/README.md), [LICENSE.md](https://github.com/janestreet/async/blob/master/LICENSE.md), [src/README.txt](https://github.com/janestreet/async/blob/master/src/README.txt), [async_rpc/README.md](https://github.com/janestreet/async/blob/master/async_rpc/README.md), [async.opam](https://github.com/janestreet/async/blob/master/async.opam), [src/async.ml](https://github.com/janestreet/async/blob/master/src/async.ml), [src/expect_test_config.ml](https://github.com/janestreet/async/blob/master/src/expect_test_config.ml), [src/expect_test_config.mli](https://github.com/janestreet/async/blob/master/src/expect_test_config.mli), [bench/tco.ml](https://github.com/janestreet/async/blob/master/bench/tco.ml), [bench/loop.ml](https://github.com/janestreet/async/blob/master/bench/loop.ml).

## [incremental](https://github.com/janestreet/incremental)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | 입력 변화에 따른 증분 계산 |
| 아키텍처·의존성 | DAG 노드·가변 입력·stabilization; opam: ocaml, core, core_kernel, janestreet_lru_cache, ppx_jane, ppx_optcomp, textutils_kernel, dune |
| 자료구조 | 노드/의존 관계/시계 상태 |
| 처리 흐름 | 변경 → dirty 전파 → 안정화 → 관측 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | 라이브러리의 병렬 실행 보장은 선택 자료에서 미확인 |
| 오류 | 선택 소스에서 구체 오류 정책 미확인 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: test/import.ml, test/test_config.ml; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | Graph 배치 무효화·버전·전체 재계산 동등성 |

읽은 파일: [LICENSE.md](https://github.com/janestreet/incremental/blob/master/LICENSE.md), [README.org](https://github.com/janestreet/incremental/blob/master/README.org), [memoize/README.md](https://github.com/janestreet/incremental/blob/master/memoize/README.md), [incremental.opam](https://github.com/janestreet/incremental/blob/master/incremental.opam), [src/at.ml](https://github.com/janestreet/incremental/blob/master/src/at.ml), [src/at.mli](https://github.com/janestreet/incremental/blob/master/src/at.mli), [src/var.ml](https://github.com/janestreet/incremental/blob/master/src/var.ml), [test/import.ml](https://github.com/janestreet/incremental/blob/master/test/import.ml), [test/test_config.ml](https://github.com/janestreet/incremental/blob/master/test/test_config.ml).

## [bin_prot](https://github.com/janestreet/bin_prot)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | 타입 안전한 바이너리 직렬화 |
| 아키텍처·의존성 | size/read/write 및 타입 클래스 분리; opam: ocaml, base, basement, ppx_compare, ppx_custom_printf, ppx_fields_conv, ppx_globalize, ppx_optcomp, ppx_sexp_conv, ppx_stable_witness, ppx_template, ppx_variants_conv, dune |
| 자료구조 | Bigstring/버퍼 위치와 스키마 |
| 처리 흐름 | 크기 계산 → 버퍼 기록 → 검증된 읽기 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | 라이브러리의 병렬 실행 보장은 선택 자료에서 미확인 |
| 오류 | raise 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: test/import.ml, test/test_std.ml; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | Pydantic 계약·Parquet 스키마와 해시 |

읽은 파일: [README.md](https://github.com/janestreet/bin_prot/blob/master/README.md), [LICENSE.md](https://github.com/janestreet/bin_prot/blob/master/LICENSE.md), [LICENSE-Tywith.txt](https://github.com/janestreet/bin_prot/blob/master/LICENSE-Tywith.txt), [shape/README.md](https://github.com/janestreet/bin_prot/blob/master/shape/README.md), [bin_prot.opam](https://github.com/janestreet/bin_prot/blob/master/bin_prot.opam), [src/md5.ml](https://github.com/janestreet/bin_prot/blob/master/src/md5.ml), [src/std.ml](https://github.com/janestreet/bin_prot/blob/master/src/std.ml), [src/blob.ml](https://github.com/janestreet/bin_prot/blob/master/src/blob.ml), [test/import.ml](https://github.com/janestreet/bin_prot/blob/master/test/import.ml), [test/test_std.ml](https://github.com/janestreet/bin_prot/blob/master/test/test_std.ml).

## [torch](https://github.com/janestreet/torch)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | PyTorch C++ API의 OCaml 바인딩 |
| 아키텍처·의존성 | 자동 생성 바인딩·tensor/layer 모듈; opam: ocaml, base, core, core_unix, ppx_bench, ppx_expect, ppx_inline_test, ppx_jane, ppx_let, ppx_module_timer, ppx_string, stdio, ctypes, ctypes-foreign, dune, dune-configurator, ocaml-compiler-libs, libtorch |
| 자료구조 | Tensor/Var_store |
| 처리 흐름 | tensor 입력 → 연산/자동미분 → 결과 |
| 메모리 | README에서 deterministic refcounting 명시; Python MVP가 이를 재현한다고 주장하지 않음 |
| 동시성·병렬 | 라이브러리의 병렬 실행 보장은 선택 자료에서 미확인 |
| 오류 | raise, exception 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: src/tests/jit_tests.ml, src/tests/rnn_tests.ml; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | ML과 데이터 계약 분리; 현재는 sklearn baseline만 도입 |

읽은 파일: [README.md](https://github.com/janestreet/torch/blob/master/README.md), [LICENSE.md](https://github.com/janestreet/torch/blob/master/LICENSE.md), [LICENSE_NOTES](https://github.com/janestreet/torch/blob/master/LICENSE_NOTES), [examples/gan/README.md](https://github.com/janestreet/torch/blob/master/examples/gan/README.md), [torch.opam](https://github.com/janestreet/torch/blob/master/torch.opam), [src/torch/cuda.ml](https://github.com/janestreet/torch/blob/master/src/torch/cuda.ml), [src/vision/vgg.ml](https://github.com/janestreet/torch/blob/master/src/vision/vgg.ml), [src/torch/cuda.mli](https://github.com/janestreet/torch/blob/master/src/torch/cuda.mli), [src/tests/jit_tests.ml](https://github.com/janestreet/torch/blob/master/src/tests/jit_tests.ml), [src/tests/rnn_tests.ml](https://github.com/janestreet/torch/blob/master/src/tests/rnn_tests.ml).

## [hardcaml](https://github.com/janestreet/hardcaml)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | 하드웨어 회로 설계·시뮬레이션·RTL 생성 |
| 아키텍처·의존성 | Signal과 회로 변환/시뮬레이터 분리; opam: ocaml, base, bignum, core, core_kernel, jane_rope, ppx_compare, ppx_jane, ppx_rope, ppx_sexp_conv, sexplib, stdio, dune, ppxlib |
| 자료구조 | Signal/회로/포트/RAM |
| 처리 흐름 | 설계 → 시뮬레이션 → RTL 출력 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | 라이브러리의 병렬 실행 보장은 선택 자료에서 미확인 |
| 오류 | Or_error, raise, exception 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: test/lib/import.ml, test/bench/import.ml; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | 결정론적 상태 전이 검증 철학; FPGA는 미도입 |

읽은 파일: [README.md](https://github.com/janestreet/hardcaml/blob/master/README.md), [LICENSE.md](https://github.com/janestreet/hardcaml/blob/master/LICENSE.md), [test/rtl/README](https://github.com/janestreet/hardcaml/blob/master/test/rtl/README), [test/rtl_gen/README.md](https://github.com/janestreet/hardcaml/blob/master/test/rtl_gen/README.md), [hardcaml.opam](https://github.com/janestreet/hardcaml/blob/master/hardcaml.opam), [src/ram.ml](https://github.com/janestreet/hardcaml/blob/master/src/ram.ml), [src/rtl.ml](https://github.com/janestreet/hardcaml/blob/master/src/rtl.ml), [src/vcd.ml](https://github.com/janestreet/hardcaml/blob/master/src/vcd.ml), [test/lib/import.ml](https://github.com/janestreet/hardcaml/blob/master/test/lib/import.ml), [test/bench/import.ml](https://github.com/janestreet/hardcaml/blob/master/test/bench/import.ml).

## [magic-trace](https://github.com/janestreet/magic-trace)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | 프로그램 실행 추적과 분석 도구 |
| 아키텍처·의존성 | 수집/추적 분석/시각화 도구 구성; opam: ocaml, ocamlformat, ocaml_intrinsics, async, camlzip, cohttp, cohttp_static_handler, core, core_unix, expect_test_helpers_async, crunch, ppx_jane, shell, dune, owee, re, zstandard, vec, core_kernel |
| 자료구조 | 추적 이벤트·압축된 실행 정보 |
| 처리 흐름 | 실행 추적 → 분석 → 시각화 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | 라이브러리의 병렬 실행 보장은 선택 자료에서 미확인 |
| 오류 | Result, exception 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. 도구/trace/반복 표본 분석을 제공; QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: test/test.ml, test/test.mli; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | 실측 후 최적화; perf_counter 지연 분포 구현 |

읽은 파일: [README.md](https://github.com/janestreet/magic-trace/blob/master/README.md), [LICENSE.md](https://github.com/janestreet/magic-trace/blob/master/LICENSE.md), [demo/README.md](https://github.com/janestreet/magic-trace/blob/master/demo/README.md), [direct_backend/README.md](https://github.com/janestreet/magic-trace/blob/master/direct_backend/README.md), [magic-trace.opam](https://github.com/janestreet/magic-trace/blob/master/magic-trace.opam), [vendor/fzf/fzf.opam](https://github.com/janestreet/magic-trace/blob/master/vendor/fzf/fzf.opam), [src/elf.ml](https://github.com/janestreet/magic-trace/blob/master/src/elf.ml), [src/elf.mli](https://github.com/janestreet/magic-trace/blob/master/src/elf.mli), [src/util.ml](https://github.com/janestreet/magic-trace/blob/master/src/util.ml), [test/test.ml](https://github.com/janestreet/magic-trace/blob/master/test/test.ml), [test/test.mli](https://github.com/janestreet/magic-trace/blob/master/test/test.mli).

## [core_bench](https://github.com/janestreet/core_bench)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | OCaml 마이크로벤치마크 도구 |
| 아키텍처·의존성 | 측정과 분석 및 runner 분리; opam: ocaml, command_nodejs, core, core_extended, core_kernel, core_unix, delimited_parsing, ppx_bench, ppx_compare, ppx_fields_conv, ppx_jane, ppx_let, ppx_optcomp, ppx_sexp_conv, textutils, time_now, dune, js_of_ocaml-ppx, re |
| 자료구조 | 측정 표본/분석 결과 |
| 처리 흐름 | 작업 반복 → 표본 수집 → 비교 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | 라이브러리의 병렬 실행 보장은 선택 자료에서 미확인 |
| 오류 | Or_error, Result 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. 도구/trace/반복 표본 분석을 제공; QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: src/bench.ml, src/bench.mli, test/tsc.ml; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | 워밍업·분포·환경을 남기는 DAG/API 벤치마크 |

읽은 파일: [README.md](https://github.com/janestreet/core_bench/blob/master/README.md), [LICENSE.md](https://github.com/janestreet/core_bench/blob/master/LICENSE.md), [js/README.md](https://github.com/janestreet/core_bench/blob/master/js/README.md), [core_bench.opam](https://github.com/janestreet/core_bench/blob/master/core_bench.opam), [src/bench.ml](https://github.com/janestreet/core_bench/blob/master/src/bench.ml), [src/hooks.ml](https://github.com/janestreet/core_bench/blob/master/src/hooks.ml), [src/bench.mli](https://github.com/janestreet/core_bench/blob/master/src/bench.mli), [test/tsc.ml](https://github.com/janestreet/core_bench/blob/master/test/tsc.ml).

## [memtrace](https://github.com/janestreet/memtrace)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | OCaml Memprof 메모리 추적 |
| 아키텍처·의존성 | streaming 기록과 viewer 분석 분리; opam: ocaml, base-threads, dune |
| 자료구조 | 할당/수거 이벤트와 공유 writer |
| 처리 흐름 | 할당 표본 → compact trace → 메모리 분석 |
| 메모리 | Memprof 할당/수거 표본 기록과 shared writer lock 확인; 자체 메모리 효율은 미측정 |
| 동시성·병렬 | 라이브러리의 병렬 실행 보장은 선택 자료에서 미확인 |
| 오류 | raise, exception 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. 도구/trace/반복 표본 분석을 제공; QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: test/copy.ml, test/fork.ml; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | Python peak RSS 측정; 누수 분석은 후속 |

읽은 파일: [README.md](https://github.com/janestreet/memtrace/blob/master/README.md), [LICENSE.md](https://github.com/janestreet/memtrace/blob/master/LICENSE.md), [trace_ocamlopt/README.md](https://github.com/janestreet/memtrace/blob/master/trace_ocamlopt/README.md), [memtrace.opam](https://github.com/janestreet/memtrace/blob/master/memtrace.opam), [src/buf.ml](https://github.com/janestreet/memtrace/blob/master/src/buf.ml), [src/buf.mli](https://github.com/janestreet/memtrace/blob/master/src/buf.mli), [src/lock.ml](https://github.com/janestreet/memtrace/blob/master/src/lock.ml), [test/copy.ml](https://github.com/janestreet/memtrace/blob/master/test/copy.ml), [test/fork.ml](https://github.com/janestreet/memtrace/blob/master/test/fork.ml).

## [bonsai](https://github.com/janestreet/bonsai)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | 반응형 OCaml UI 라이브러리 |
| 아키텍처·의존성 | 함수형 상태 머신과 증분 렌더링; opam: ocaml, abstract_algebra, async_rpc_kernel, base, bonsai_concrete, core, core_kernel, incr_map, incremental, ocaml-embed-file, ppx_here, ppx_jane, ppx_let, ppx_pattern_bind, ppxlib_jane, virtual_dom, dune, js_of_ocaml-ppx, ppxlib |
| 자료구조 | 상태/Effect/Incr.Var |
| 처리 흐름 | 상태 갱신 → 의존 계산 → UI 효과 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | 라이브러리의 병렬 실행 보장은 선택 자료에서 미확인 |
| 오류 | raise, exception 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 선택 파일에 독립 테스트/벤치 없음; inline/다른 저장소 검증을 추정하지 않음; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | React 상태·WebSocket snapshot·계산과 표시 분리 |

읽은 파일: [README.md](https://github.com/janestreet/bonsai/blob/master/README.md), [LICENSE.md](https://github.com/janestreet/bonsai/blob/master/LICENSE.md), [ppx_bonsai/readme.md](https://github.com/janestreet/bonsai/blob/master/ppx_bonsai/readme.md), [trampoline/README.md](https://github.com/janestreet/bonsai/blob/master/trampoline/README.md), [bonsai.opam](https://github.com/janestreet/bonsai/blob/master/bonsai.opam), [src/var.ml](https://github.com/janestreet/bonsai/blob/master/src/var.ml), [src/cont.ml](https://github.com/janestreet/bonsai/blob/master/src/cont.ml), [src/proc.ml](https://github.com/janestreet/bonsai/blob/master/src/proc.ml), [bench_scenario/bonsai_bench_scenario.ml](https://github.com/janestreet/bonsai/blob/master/bench_scenario/bonsai_bench_scenario.ml), [bench_scenario/bonsai_bench_scenario.mli](https://github.com/janestreet/bonsai/blob/master/bench_scenario/bonsai_bench_scenario.mli).

## [rpc_parallel](https://github.com/janestreet/rpc_parallel)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | 타입 안전한 프로세스 worker RPC |
| 아키텍처·의존성 | worker 상태와 connection 상태 구분; opam: ocaml, async, core, core_kernel, core_unix, current_exe, ppx_jane, dune |
| 자료구조 | worker ID/연결/RPC 함수 |
| 처리 흐름 | spawn → typed RPC → worker 결과 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | worker spawn과 RPC 함수/connection 상태 분리 확인; 실제 실행 안함 |
| 오류 | Or_error, Result, raise, exception 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: test/fd.ml, test/fd.mli; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | fault isolation 참고; 분산 프로세스 미도입 |

읽은 파일: [LICENSE.md](https://github.com/janestreet/rpc_parallel/blob/master/LICENSE.md), [rpc_parallel.opam](https://github.com/janestreet/rpc_parallel/blob/master/rpc_parallel.opam), [src/utils.ml](https://github.com/janestreet/rpc_parallel/blob/master/src/utils.ml), [src/utils.mli](https://github.com/janestreet/rpc_parallel/blob/master/src/utils.mli), [src/managed.ml](https://github.com/janestreet/rpc_parallel/blob/master/src/managed.ml), [test/fd.ml](https://github.com/janestreet/rpc_parallel/blob/master/test/fd.ml), [test/fd.mli](https://github.com/janestreet/rpc_parallel/blob/master/test/fd.mli).

## [parallel](https://github.com/janestreet/parallel)

라이선스: 미확인: 라이선스 파일을 확보하지 못해 코드 도입하지 않음.

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | OxCaml Parallelism이라는 README만 확인 |
| 아키텍처·의존성 | 실제 구현 파일 없음; opam: 미확인 |
| 자료구조 | 미확인 |
| 처리 흐름 | 미확인 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | README의 명칭 이외 구현과 동기화 세부사항 미확인 |
| 오류 | 선택 소스에서 구체 오류 정책 미확인 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 선택 파일에 독립 테스트/벤치 없음; inline/다른 저장소 검증을 추정하지 않음; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | 구현/라이선스 확인 전 도입하지 않음 |

읽은 파일: [README.md](https://github.com/janestreet/parallel/blob/master/README.md).

## [bignum](https://github.com/janestreet/bignum)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | 임의 정밀도 유리수/큰 수 연산 |
| 아키텍처·의존성 | Zarith 기반 수치 타입; opam: ocaml, core, ppx_jane, ppx_stable_witness, sexplib, typerep, zarith_stubs_js, dune, num, zarith |
| 자료구조 | 정수·유리수/큰 정수 |
| 처리 흐름 | 정밀 값 → 산술 → 문자열/표현 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | 라이브러리의 병렬 실행 보장은 선택 자료에서 미확인 |
| 오류 | Or_error, raise, exception 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: bench/bignum_bench.ml, bench/bignum_bench.mli; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | 금전 원장 Decimal과 float 통계의 경계 설정 |

읽은 파일: [LICENSE.md](https://github.com/janestreet/bignum/blob/master/LICENSE.md), [bignum.opam](https://github.com/janestreet/bignum/blob/master/bignum.opam), [src/bignum.ml](https://github.com/janestreet/bignum/blob/master/src/bignum.ml), [src/zarith.ml](https://github.com/janestreet/bignum/blob/master/src/zarith.ml), [src/bignum.mli](https://github.com/janestreet/bignum/blob/master/src/bignum.mli), [bench/bignum_bench.ml](https://github.com/janestreet/bignum/blob/master/bench/bignum_bench.ml), [bench/bignum_bench.mli](https://github.com/janestreet/bignum/blob/master/bench/bignum_bench.mli).

## [bigdecimal](https://github.com/janestreet/bigdecimal)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | 고정밀 십진수 표현 |
| 아키텍처·의존성 | mantissa×10^exponent 표현; opam: ocaml, bignum, core, ppx_jane, ppx_stable_witness, dune, zarith |
| 자료구조 | Bigint mantissa와 정수 exponent |
| 처리 흐름 | 십진 입력 → 정밀 연산 → 십진 출력 |
| 메모리 | Bigint mantissa/exponent 표현 확인; 할당/GC 최적화 효과는 미측정 |
| 동시성·병렬 | 라이브러리의 병렬 실행 보장은 선택 자료에서 미확인 |
| 오류 | Or_error, raise, exception 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 선택 파일에 독립 테스트/벤치 없음; inline/다른 저장소 검증을 추정하지 않음; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | Decimal 원장·명시적 반올림·정수 수량 |

읽은 파일: [LICENSE.md](https://github.com/janestreet/bigdecimal/blob/master/LICENSE.md), [bigdecimal.opam](https://github.com/janestreet/bigdecimal/blob/master/bigdecimal.opam), [src/zarith.ml](https://github.com/janestreet/bigdecimal/blob/master/src/zarith.ml), [src/bigdecimal.ml](https://github.com/janestreet/bigdecimal/blob/master/src/bigdecimal.ml), [src/bigdecimal.mli](https://github.com/janestreet/bigdecimal/blob/master/src/bigdecimal.mli).

## [base_quickcheck](https://github.com/janestreet/base_quickcheck)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | 무작위 속성 기반 검사 |
| 아키텍처·의존성 | generator/observer/shrinker/test 분리; opam: ocaml, base, basement, ppx_base, ppx_fields_conv, ppx_helpers, ppx_let, ppx_portable, ppx_sexp_message, ppx_sexp_value, ppx_shorthand, ppx_template, ppxlib_jane, splittable_random, dune, ppxlib |
| 자료구조 | 생성기·축소기·설정 seed |
| 처리 흐름 | 생성 → 속성 실행 → 실패 사례 축소 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | 라이브러리의 병렬 실행 보장은 선택 자료에서 미확인 |
| 오류 | Or_error, raise 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: src/test.ml, src/test.mli; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | Hypothesis 증분 일치/옵션 parity 속성 검사 |

읽은 파일: [LICENSE.md](https://github.com/janestreet/base_quickcheck/blob/master/LICENSE.md), [ppx_quickcheck/README.md](https://github.com/janestreet/base_quickcheck/blob/master/ppx_quickcheck/README.md), [base_quickcheck.opam](https://github.com/janestreet/base_quickcheck/blob/master/base_quickcheck.opam), [src/test.ml](https://github.com/janestreet/base_quickcheck/blob/master/src/test.ml), [src/test.mli](https://github.com/janestreet/base_quickcheck/blob/master/src/test.mli), [src/export.ml](https://github.com/janestreet/base_quickcheck/blob/master/src/export.ml).

## [ppx_jane](https://github.com/janestreet/ppx_jane)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | 표준 PPX 전처리기 묶음 |
| 아키텍처·의존성 | opam 의존성으로 여러 PPX 조합; opam: ocaml, base_quickcheck, ppx_assert, ppx_base, ppx_bench, ppx_bin_prot, ppx_custom_printf, ppx_debug_assert, ppx_disable_unused_warnings, ppx_expect, ppx_fields_conv, ppx_fixed_literal, ppx_here, ppx_ignore_instrumentation, ppx_inline_test, ppx_int63_literal, ppx_let, ppx_log, ppx_module_timer, ppx_optional, ppx_pipebang, ppx_sexp_message, ppx_sexp_value, ppx_shorthand, ppx_stable, ppx_stable_witness, ppx_string, ppx_string_conv, ppx_template, ppx_tydi, ppx_typed_fields, ppx_typerep_conv, ppx_var_name, ppx_variants_conv, dune, ppxlib |
| 자료구조 | OCaml AST 변환 구성 |
| 처리 흐름 | 타입/구문 → 전처리 → 생성 코드 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | 라이브러리의 병렬 실행 보장은 선택 자료에서 미확인 |
| 오류 | 선택 소스에서 구체 오류 정책 미확인 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: test/alert_in_ml/ppx_jane_test_alert_in_ml.ml, test/alert_in_mli/ppx_jane_test_alert_in_mli.ml; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | 자동 계약과 회귀 출력 검사 철학; PPX 자체 사용 안함 |

읽은 파일: [README.md](https://github.com/janestreet/ppx_jane/blob/master/README.md), [LICENSE.md](https://github.com/janestreet/ppx_jane/blob/master/LICENSE.md), [ppx_jane.opam](https://github.com/janestreet/ppx_jane/blob/master/ppx_jane.opam), [src/ppx_jane.ml](https://github.com/janestreet/ppx_jane/blob/master/src/ppx_jane.ml), [test/alert_in_ml/ppx_jane_test_alert_in_ml.ml](https://github.com/janestreet/ppx_jane/blob/master/test/alert_in_ml/ppx_jane_test_alert_in_ml.ml), [test/alert_in_mli/ppx_jane_test_alert_in_mli.ml](https://github.com/janestreet/ppx_jane/blob/master/test/alert_in_mli/ppx_jane_test_alert_in_mli.ml).

## [async_rpc_kernel](https://github.com/janestreet/async_rpc_kernel)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | 이식 가능한 비동기 RPC 프로토콜 |
| 아키텍처·의존성 | RPC 인터페이스와 서버 구현 분리; opam: ocaml, async_kernel, bin_prot, core, core_extended, core_kernel, flexible_sexp, pipe_with_writer_error, ppx_jane, ppx_stable_witness, protocol_version_header, sexplib, dune |
| 자료구조 | Rpc/State_rpc/Pipe_rpc/transport |
| 처리 흐름 | 요청 → 프로토콜 해석 → 구현 → 응답 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | Async/Deferred 기반 비동기 I/O 확인; CPU 병렬성과 구분 |
| 오류 | Or_error, Result, raise, exception 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: bench/bench.ml, test/import.ml; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | API 응답 스키마·일회용 WS ticket |

읽은 파일: [README.md](https://github.com/janestreet/async_rpc_kernel/blob/master/README.md), [LICENSE.md](https://github.com/janestreet/async_rpc_kernel/blob/master/LICENSE.md), [async_rpc_kernel.opam](https://github.com/janestreet/async_rpc_kernel/blob/master/async_rpc_kernel.opam), [src/rpc.ml](https://github.com/janestreet/async_rpc_kernel/blob/master/src/rpc.ml), [src/rpc.mli](https://github.com/janestreet/async_rpc_kernel/blob/master/src/rpc.mli), [src/util.ml](https://github.com/janestreet/async_rpc_kernel/blob/master/src/util.ml), [bench/bench.ml](https://github.com/janestreet/async_rpc_kernel/blob/master/bench/bench.ml), [test/import.ml](https://github.com/janestreet/async_rpc_kernel/blob/master/test/import.ml).

## [ocaml_simd](https://github.com/janestreet/ocaml_simd)

라이선스: 미확인: 라이선스 파일을 확보하지 못해 코드 도입하지 않음.

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | OxCaml SIMD intrinsics라는 README만 확인 |
| 아키텍처·의존성 | 실제 구현 파일 없음; opam: 미확인 |
| 자료구조 | 미확인 |
| 처리 흐름 | 미확인 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | README의 명칭 이외 구현과 동기화 세부사항 미확인 |
| 오류 | 선택 소스에서 구체 오류 정책 미확인 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 선택 파일에 독립 테스트/벤치 없음; inline/다른 저장소 검증을 추정하지 않음; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | 프로파일링 증거 없으므로 SIMD 확장 미도입 |

읽은 파일: [README.md](https://github.com/janestreet/ocaml_simd/blob/master/README.md).

## [ocaml_intrinsics](https://github.com/janestreet/ocaml_intrinsics)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | 하드웨어 명령의 OCaml 인터페이스 |
| 아키텍처·의존성 | intrinsic/C stub fallback; opam: ocaml, basement, ocaml_intrinsics_kernel, ppx_builtin, dune, ocaml-compiler-libs |
| 자료구조 | 정수·CRC/명령 wrapper |
| 처리 흐름 | 호출 → 하드웨어 또는 fallback → 결과 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | 라이브러리의 병렬 실행 보장은 선택 자료에서 미확인 |
| 오류 | raise 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: bench/bench.ml, test/import.ml; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | 측정 전 intrinsics 사용하지 않음 |

읽은 파일: [README.md](https://github.com/janestreet/ocaml_intrinsics/blob/master/README.md), [LICENSE.md](https://github.com/janestreet/ocaml_intrinsics/blob/master/LICENSE.md), [ocaml_intrinsics.opam](https://github.com/janestreet/ocaml_intrinsics/blob/master/ocaml_intrinsics.opam), [src/crc.ml](https://github.com/janestreet/ocaml_intrinsics/blob/master/src/crc.ml), [src/int.ml](https://github.com/janestreet/ocaml_intrinsics/blob/master/src/int.ml), [src/crc.mli](https://github.com/janestreet/ocaml_intrinsics/blob/master/src/crc.mli), [bench/bench.ml](https://github.com/janestreet/ocaml_intrinsics/blob/master/bench/bench.ml), [test/import.ml](https://github.com/janestreet/ocaml_intrinsics/blob/master/test/import.ml).

## [postgres_async](https://github.com/janestreet/postgres_async)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | PostgreSQL wire protocol 클라이언트 |
| 아키텍처·의존성 | Async 기반 질의/파라미터/COPY 지원; opam: ocaml, async, async_kernel, async_ssl, async_unix, core, core_kernel, ppx_jane, base64, cryptokit, dune, kdf |
| 자료구조 | 연결·query·SSL mode |
| 처리 흐름 | 파라미터 질의 → 프로토콜 I/O → 결과 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | Async/Deferred 기반 비동기 I/O 확인; CPU 병렬성과 구분 |
| 오류 | Or_error 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: test/utils.ml, test/utils.mli; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | 파라미터 SQL·저장소 추상화, MVP는 SQLite |

읽은 파일: [README.md](https://github.com/janestreet/postgres_async/blob/master/README.md), [LICENSE.md](https://github.com/janestreet/postgres_async/blob/master/LICENSE.md), [postgres_async.opam](https://github.com/janestreet/postgres_async/blob/master/postgres_async.opam), [src/crypto.ml](https://github.com/janestreet/postgres_async/blob/master/src/crypto.ml), [src/ssl_mode.ml](https://github.com/janestreet/postgres_async/blob/master/src/ssl_mode.ml), [src/ssl_mode.mli](https://github.com/janestreet/postgres_async/blob/master/src/ssl_mode.mli), [test/utils.ml](https://github.com/janestreet/postgres_async/blob/master/test/utils.ml), [test/utils.mli](https://github.com/janestreet/postgres_async/blob/master/test/utils.mli).

## [redis-async](https://github.com/janestreet/redis-async)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | Async 기반 Redis RESP3 클라이언트 |
| 아키텍처·의존성 | typed serializer와 연결/역할 모듈; opam: ocaml, async, bignum, core, core_kernel, ppx_jane, dune |
| 자료구조 | 인증/role/연결/typed payload |
| 처리 흐름 | 명령 → RESP3 → typed 응답 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | Async/Deferred 기반 비동기 I/O 확인; CPU 병렬성과 구분 |
| 오류 | Or_error, Result 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: test/leak.ml, test/sandbox.ml; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | 캐시 경계·실패 격리; Redis 의존성 보류 |

읽은 파일: [README.md](https://github.com/janestreet/redis-async/blob/master/README.md), [LICENSE.md](https://github.com/janestreet/redis-async/blob/master/LICENSE.md), [redis-async.opam](https://github.com/janestreet/redis-async/blob/master/redis-async.opam), [src/auth.ml](https://github.com/janestreet/redis-async/blob/master/src/auth.ml), [src/role.ml](https://github.com/janestreet/redis-async/blob/master/src/role.ml), [src/sha1.ml](https://github.com/janestreet/redis-async/blob/master/src/sha1.ml), [test/leak.ml](https://github.com/janestreet/redis-async/blob/master/test/leak.ml), [test/sandbox.ml](https://github.com/janestreet/redis-async/blob/master/test/sandbox.ml).

## [incr_map](https://github.com/janestreet/incr_map)

라이선스: MIT (LICENSE/opam 확인).

| 조사 항목 | 확인 / 적용 판단 |
|---|---|
| 핵심 기능 | Map 연산의 증분 계산 |
| 아키텍처·의존성 | Incremental과 Map diff 조합; opam: ocaml, abstract_algebra, bignum, core, incremental, legacy_diffable, ppx_diff, ppx_jane, ppx_pattern_bind, ppx_stable_witness, streamable, dune |
| 자료구조 | Map/symmetric diff/증분 노드 |
| 처리 흐름 | map 변경분 → 연산 → 새 증분 결과 |
| 메모리 | 별도 메모리 전략은 선택한 파일만으로 미확인; 성능 특성을 일반화하지 않음 |
| 동시성·병렬 | 라이브러리의 병렬 실행 보장은 선택 자료에서 미확인 |
| 오류 | raise, exception 구문을 선택 소스에서 확인; 모든 오류 경로를 검증하지 않음 |
| 성능 | 공개 설계의 선택적/타입별 계산 원칙 참고. QuantCore 속도 향상은 별도 실제 벤치마크로만 판단 |
| 테스트·검증 | 읽은 테스트/벤치: test/import.ml, test/test_sum.ml; 원본 OCaml 테스트 미실행 |
| QuantCore 적용 | 바뀐 종목의 DAG 가지를 갱신 |

읽은 파일: [LICENSE.md](https://github.com/janestreet/incr_map/blob/master/LICENSE.md), [README.org](https://github.com/janestreet/incr_map/blob/master/README.org), [collate/README.md](https://github.com/janestreet/incr_map/blob/master/collate/README.md), [erase_key/README.md](https://github.com/janestreet/incr_map/blob/master/erase_key/README.md), [incr_map.opam](https://github.com/janestreet/incr_map/blob/master/incr_map.opam), [src/incr_map.ml](https://github.com/janestreet/incr_map/blob/master/src/incr_map.ml), [src/incr_map.mli](https://github.com/janestreet/incr_map/blob/master/src/incr_map.mli), [src/incr_map_intf.ml](https://github.com/janestreet/incr_map/blob/master/src/incr_map_intf.ml), [test/import.ml](https://github.com/janestreet/incr_map/blob/master/test/import.ml), [test/test_sum.ml](https://github.com/janestreet/incr_map/blob/master/test/test_sum.ml).

## 라이선스와 추정의 경계

확인된 라이선스는 해당 저장소 상위 LICENSE와 opam 기준이다. 코드 복사·바인딩 도입 없이 개념을 참고해 새 Python 코드를 작성했다. `parallel`, `ocaml_simd`는 이번 archive가 README 1개뿐이어서 소스·테스트·라이선스를 확인하지 못했다. 공개 문서가 내부 사용을 언급하더라도 내부 전략·수익·인프라 세부사항으로 확대 추측하지 않는다.
