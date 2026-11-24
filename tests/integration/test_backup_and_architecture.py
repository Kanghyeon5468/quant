import ast
import sqlite3
from pathlib import Path

import pytest

from scripts.backup import backup


def test_online_backup_and_restore_into_new_file(service, tmp_path):
    destination = tmp_path/'backup.sqlite3'
    result = backup(service.store.directory/'quantcore.sqlite3', destination)
    assert result['integrity'] == 'ok' and len(result['sha256']) == 64
    with sqlite3.connect(destination) as c:
        assert c.execute('SELECT count(*) FROM bars').fetchone()[0] == 4680
    with pytest.raises(ValueError):
        backup(service.store.directory/'quantcore.sqlite3', destination)


def test_no_circular_module_dependencies():
    paths = list(Path('quantcore').rglob('*.py'))
    modules = {'.'.join(p.with_suffix('').parts): p for p in paths}
    graph = {}
    for module, path in modules.items():
        imports = []
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module in modules:
                imports.append(node.module)
            if isinstance(node, ast.Import):
                imports.extend(a.name for a in node.names if a.name in modules)
        graph[module] = imports
    active, done = set(), set()
    def visit(module):
        assert module not in active, f'circular dependency: {module}'
        if module in done:
            return
        active.add(module)
        for dependency in graph[module]:
            visit(dependency)
        active.remove(module)
        done.add(module)
    for module in graph:
        visit(module)
