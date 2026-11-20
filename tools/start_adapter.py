"""Start the local USB adapter, or explicitly restart it when idle."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

base = Path(__file__).resolve().parents[1]
unit = os.environ.get('WZL_ADAPTER_UNIT', 'weazlops-grab-go-adapter')
port = str(int(os.environ.get('WZL_ADAPTER_PORT', '5015')))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--ensure-running', action='store_true',
                    help='Keep a healthy running adapter and its current jobs')
options = parser.parse_args()
token_path = base / '.runtime/private/worker.token'
request = urllib.request.Request(f'http://127.0.0.1:{port}/health', headers={
    'Authorization': 'Bearer ' + token_path.read_text().strip()
})


def health():
    deadline = time.monotonic() + 10
    while True:
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                status = json.load(response)
            if status['ready'] and status['transport'] == 'native-usb':
                return status
            raise SystemExit('Unexpected adapter health response')
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(.2)


if subprocess.run(['systemctl', '--user', 'is-active', '--quiet', unit]).returncode == 0:
    status = health()
    if options.ensure_running:
        sys.exit(0)
    if status['active']:
        sys.exit('Adapter is busy; finish current device work before restart')
    subprocess.run(['systemctl', '--user', 'stop', unit], check=True)
    # systemd must unload a stopped transient unit before reusing its name.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = subprocess.run(['systemctl', '--user', 'show', unit, '-p', 'LoadState',
                                '--value'], capture_output=True, text=True)
        if state.stdout.strip() == 'not-found':
            break
        time.sleep(.1)

env = {'WZL_PRIVATE': base / '.runtime/adapter', 'WZL_WORKER_TOKEN': token_path}
if allow := os.environ.get('WZL_BENCH_ALLOWLIST'):
    env['WZL_BENCH_ALLOWLIST'] = Path(allow).resolve()
deny = base / '.runtime/private/device-denylist.json'
if deny.is_file():
    env['WZL_DEVICE_DENYLIST'] = deny
args = ['systemd-run', '--user', '--unit=' + unit, '--collect',
        '--property=Restart=on-failure', '--working-directory=' + str(base)]
args.extend(f'--setenv={key}={value}' for key, value in env.items())
python = os.environ.get('WZL_ADAPTER_PYTHON', sys.executable)
subprocess.run(args + [python, '-m', 'uvicorn', 'app.worker:app', '--host', '127.0.0.1',
                       '--port', port, '--no-access-log'], check=True)
health()
