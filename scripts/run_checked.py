#!/usr/bin/env python3
"""Run a real build/test with a deadline, preserving output and exit status."""
import argparse
from pathlib import Path
import subprocess
import sys

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--timeout', type=float, default=30)
    p.add_argument('--log', required=True)
    p.add_argument('command', nargs=argparse.REMAINDER)
    a = p.parse_args()
    cmd = a.command[1:] if a.command[:1] == ['--'] else a.command
    if not cmd or a.timeout <= 0:
        p.error('a command and positive timeout are required')
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=a.timeout, check=False)
        data, rc = r.stdout, r.returncode
    except subprocess.TimeoutExpired as e:
        data = (e.stdout or b'') + b'\nTEST_RESULT: FAIL TIMEOUT\n'
        rc = 124
    except OSError as e:
        data = ('TEST_RESULT: FAIL COMMAND_UNAVAILABLE: %s\n' % e).encode()
        rc = 127
    log = Path(a.log)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(data)
    sys.stdout.buffer.write(data)
    return rc if rc >= 0 else 1
if __name__ == '__main__':
    sys.exit(main())
