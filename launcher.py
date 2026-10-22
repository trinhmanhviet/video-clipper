"""Keep the dedicated PC backend and its tunnel running while logged in."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOGS = BASE / 'data' / 'logs'
LOGS.mkdir(parents=True, exist_ok=True)


def listening(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=2):
            return True
    except OSError:
        return False


def launch(name, command):
    with (LOGS / (name + '.log')).open('ab') as output:
        child = subprocess.Popen(command, cwd=BASE, stdin=subprocess.DEVNULL,
                                 stdout=output, stderr=subprocess.STDOUT,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (BASE / 'data' / (name + '.pid')).write_text(str(child.pid))


if __name__ == '__main__':
    # One supervisor only, including when the scheduled task is run manually.
    guard = socket.socket()
    try:
        guard.bind(('127.0.0.1', 8791))
        guard.listen(1)
    except OSError:
        sys.exit(0)
    cloudflared = os.environ.get('CLIP_CLOUDFLARED', r'C:\Program Files (x86)\cloudflared\cloudflared.exe')
    while True:
        if not listening(8790):
            launch('backend', [sys.executable, str(BASE / 'studio.py')])
        if not listening(20248):
            launch('tunnel', [cloudflared, 'tunnel', '--config', str(BASE / 'tunnel' / 'config.yml'),
                              '--no-autoupdate', 'run'])
        time.sleep(10)
