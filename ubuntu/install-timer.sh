#!/usr/bin/env bash
# Install unit files only. Never enable, start or reload systemd here.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
if (( EUID != 0 )); then
    printf '%s
' 'Run with sudo bash install-timer.sh' >&2
    exit 1
fi
[[ -x /usr/bin/python3 ]] || { printf '%s
' 'Missing /usr/bin/python3' >&2; exit 1; }
[[ -d /run/systemd/system ]] || { printf '%s
' 'systemd is required' >&2; exit 1; }
for unit in run-workflow-api.timer run-workflow-api.service; do
    if systemctl is-active --quiet "$unit"; then
        printf 'Refusing to overwrite active unit: %s. Stop it explicitly first.
' "$unit" >&2
        exit 1
    fi
done
/usr/bin/python3 - "$ROOT" <<'PY'
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

root = Path(sys.argv[1])
# systemd specifiers and quoted ExecStart paths must remain unambiguous.
if any(c in str(root) for c in '\"%$\\\n\r'):
    raise SystemExit('Unsupported character in source path')
if str(root).startswith(('/tmp/', '/var/tmp/')):
    raise SystemExit('Use a persistent readable path such as /data/sync/scripts/run_workflow_api/ubuntu')
for name in ('oci_workflow_watchdog.py', 'run-workflow-api.service.in',
             'run-workflow-api.timer', 'watchdog.env.example'):
    if not (root / name).is_file():
        raise SystemExit(f'Missing {name}')

units = Path('/etc/systemd/system')
conf = Path('/etc/run-workflow-api')
conf.mkdir(mode=0o700, parents=True, exist_ok=True)
env = conf / 'watchdog.env'
if not env.exists():
    fd = os.open(env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
        f.write((root / 'watchdog.env.example').read_text(encoding='utf-8'))

stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
service = (root / 'run-workflow-api.service.in').read_text(encoding='utf-8').replace('@ROOT@', str(root))
timer = (root / 'run-workflow-api.timer').read_text(encoding='utf-8')
for name, text in (('run-workflow-api.service', service), ('run-workflow-api.timer', timer)):
    dest = units / name
    if dest.exists():
        shutil.copy2(dest, dest.with_name(dest.name + '.' + stamp + '.bak'))
    dest.write_text(text, encoding='utf-8', newline='\n')
    dest.chmod(0o644)
    print(f'Installed {dest}')
print('Existing credentials were preserved. No daemon-reload or start performed.')
PY
printf '%s
' \
    'Next: sudoedit /etc/run-workflow-api/watchdog.env' \
    'The service runs as root with read-only filesystem protection.' \
    'Then explicitly: sudo systemctl daemon-reload' \
    'Then explicitly: sudo systemctl enable --now run-workflow-api.timer'
