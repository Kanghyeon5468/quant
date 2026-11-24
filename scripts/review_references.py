"""Read public repositories without executing or vendoring their source code."""
import concurrent.futures
import hashlib
import io
import json
import tarfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPOSITORIES = "base core async incremental bin_prot torch hardcaml magic-trace core_bench memtrace bonsai rpc_parallel parallel bignum bigdecimal base_quickcheck ppx_jane async_rpc_kernel ocaml_simd ocaml_intrinsics postgres_async redis-async incr_map".split()
CACHE = Path('/private/tmp/quantcore-references')


def inspect(repo):
    url = f'https://codeload.github.com/janestreet/{repo}/tar.gz/refs/heads/master'
    target = CACHE / f'{repo}.tar.gz'
    try:
        if not target.exists():
            request = urllib.request.Request(url, headers={'User-Agent': 'QuantCore-public-source-review/0.1'})
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read(35_000_000)
            if len(raw) >= 35_000_000:
                raise ValueError('archive exceeds review size limit')
            target.write_bytes(raw)
        raw = target.read_bytes()
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
            members = [m for m in archive.getmembers() if m.isfile() and m.size < 300_000]
            def select(predicate, count):
                return sorted([m for m in members if predicate(m.name)], key=lambda m: (m.name.count('/'), len(m.name)))[:count]
            selected = select(lambda p: Path(p).name.lower().startswith(('readme', 'license', 'copying')), 4)
            selected += select(lambda p: p.endswith('.opam'), 2)
            selected += select(lambda p: ('/src/' in p or '/lib/' in p) and p.endswith(('.mli', '.ml')), 3)
            selected += select(lambda p: ('/test' in p or '/bench' in p) and p.endswith(('.ml', '.mli')), 2)
            evidence = []
            output = []
            for member in dict.fromkeys(selected):
                data = archive.extractfile(member).read()
                relative = member.name.split('/', 1)[-1]
                evidence.append({'path': relative, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
                output.append(f'FILE {relative}\n'+data.decode(errors='replace')[:24000])
            # Review copies remain in /tmp, never in the application or public reports.
            (CACHE / f'{repo}.review.txt').write_text('\n\n'.join(output))
            names = [m.name.split('/', 1)[-1] for m in members]
        return {'repository': repo, 'url': f'https://github.com/janestreet/{repo}', 'status': 'retrieved',
                'retrieved_at': datetime.now(timezone.utc).isoformat(), 'archive_sha256': hashlib.sha256(raw).hexdigest(),
                'files': evidence, 'source_files': sum(p.endswith(('.ml', '.mli')) for p in names)}
    except (urllib.error.URLError, OSError, ValueError, tarfile.TarError) as error:
        return {'repository': repo, 'url': f'https://github.com/janestreet/{repo}', 'status': 'unavailable', 'reason': str(error)}


if __name__ == '__main__':
    CACHE.mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(inspect, REPOSITORIES))
    Path('docs/reference_evidence.json').write_text(json.dumps(records, indent=2)+'\n')
    for record in records:
        print(record['repository'], record['status'], len(record.get('files', [])))
