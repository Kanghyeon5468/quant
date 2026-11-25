"""Install/manage a 5-minute macOS LaunchAgent for explicitly authorized paper trading."""
import argparse
import json
import os
import platform
import plistlib
import subprocess
import sys
from pathlib import Path

from quantcore.paper.automation import resume, tick

LABEL = 'com.quantcore.paper-trading'


def make_plist(root, env_file):
    root = Path(root).resolve()
    logs = root/'artifacts/paper_trading/automation'
    argv = [str(root/'.venv/bin/python'), '-u', str(root/'scripts/manage_paper_automation.py'), 'tick']
    if env_file:
        argv += ['--env-file', str(Path(env_file).resolve())]
    return {'Label': LABEL, 'ProgramArguments': argv, 'WorkingDirectory': str(root),
            'RunAtLoad': True, 'StartInterval': 300, 'ThrottleInterval': 60, 'ProcessType': 'Background',
            'Umask': 0o077, 'EnvironmentVariables': {'PYTHONUNBUFFERED': '1', 'LOKY_MAX_CPU_COUNT': '2'},
            'StandardOutPath': str(logs/'launchd.stdout.log'), 'StandardErrorPath': str(logs/'launchd.stderr.log')}


def install(root, env_file):
    if platform.system() != 'Darwin':
        raise RuntimeError('automatic service installer requires macOS launchd')
    root = Path(root).resolve()
    spec = make_plist(root, env_file)
    prepared = root/'artifacts/paper_trading/automation/launchagent.plist'
    prepared.parent.mkdir(parents=True, exist_ok=True)
    prepared.write_bytes(plistlib.dumps(spec))
    prepared.chmod(0o600)
    destination = Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and plistlib.loads(destination.read_bytes()) != spec:
        raise RuntimeError('existing service configuration differs; preserve it and uninstall explicitly first')
    destination.write_bytes(prepared.read_bytes())
    destination.chmod(0o600)
    target = f'gui/{os.getuid()}/{LABEL}'
    loaded = subprocess.run(['launchctl', 'print', target], capture_output=True).returncode == 0
    if not loaded:
        subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(destination)], check=True)
    else:
        subprocess.run(['launchctl', 'kickstart', target], check=True)
    return {'label': LABEL, 'plist': str(destination), 'interval_seconds': 300, 'run_at_login': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['tick', 'status', 'install', 'pause', 'resume', 'risk-reset', 'uninstall'])
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--reason', default='')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    directory = root/'artifacts/paper_trading'
    directory.mkdir(parents=True, exist_ok=True)
    if args.command == 'tick':
        result = tick(root, args.env_file)
        print(json.dumps({k: result[k] for k in ('checked_at', 'phase', 'next_task', 'last_evaluation', 'error')
                          if k in result}))
        sys.exit(1 if result['phase'] == 'blocked' else 0)
    elif args.command == 'install':
        print(json.dumps(install(root, args.env_file), indent=2))
    elif args.command == 'pause':
        (directory/'STOP').touch()
        print('Paused: new paper orders blocked. Already accepted orders remain at Alpaca.')
    elif args.command == 'resume':
        resume(directory)
        print('Resumed: next tick reconciles broker state before considering any new order.')
    elif args.command == 'risk-reset':
        from quantcore.paper.guard import reset_drawdown
        from quantcore.paper.runner import Journal
        journal = Journal(directory)
        try:
            with journal.lock():
                print(json.dumps(reset_drawdown(journal, args.reason)))
        finally:
            journal.close()
    elif args.command == 'status':
        path = directory/'automation/state.json'
        print(path.read_text() if path.exists() else 'No automation heartbeat yet.')
        if platform.system() == 'Darwin':
            subprocess.run(['launchctl', 'print', f'gui/{os.getuid()}/{LABEL}'], check=False)
    else:
        (directory/'STOP').touch()
        path = Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
        if path.exists():
            spec = plistlib.loads(path.read_bytes())
            if (spec.get('Label') != LABEL or spec.get('WorkingDirectory') != str(root)
                    or str(root/'scripts/manage_paper_automation.py') not in spec.get('ProgramArguments', [])):
                raise RuntimeError('service file belongs to another configuration; refusing to remove it')
        target = f'gui/{os.getuid()}/{LABEL}'
        loaded = subprocess.run(['launchctl', 'print', target], capture_output=True).returncode == 0
        if loaded:
            subprocess.run(['launchctl', 'bootout', target], check=True)
        if path.exists():
            path.unlink()
        print('Automation unloaded; new orders paused. Existing accepted orders remain at Alpaca.')
