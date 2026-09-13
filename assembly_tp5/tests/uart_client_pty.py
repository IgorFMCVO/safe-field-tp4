#!/usr/bin/env python3
"""Real AArch64 client + host PTY: software integration, NEVER hardware proof."""
import argparse
import os
import pty
import re
import select
import shlex
import subprocess
import time
import tty
from pathlib import Path


def crc8(data):
    c = 0
    for byte in data:
        c ^= byte
        for _ in range(8):
            c = ((c << 1) ^ (7 if c & 0x80 else 0)) & 255
    return c


def read_exact(fd, count, timeout=3):
    data = bytearray()
    deadline = time.monotonic() + timeout
    while len(data) < count:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            raise TimeoutError('client did not send complete request')
        block = os.read(fd, count - len(data))
        if not block:
            raise EOFError('request ended early')
        data.extend(block)
    return bytes(data)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runner', default='qemu-aarch64')
    p.add_argument('--binary', default='build/tp5_uart_demo')
    args = p.parse_args()
    cases = ['valid', 'fragmented', 'payload', 'crc', 'sequence', 'version', 'error_flag', 'eof']
    for case in cases:
        master, slave = pty.openpty()
        proc = None
        try:
            tty.setraw(slave)
            proc = subprocess.Popen(shlex.split(args.runner) + [str(Path(args.binary).resolve()), os.ttyname(slave)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            request = read_exact(master, 11)
            assert request[:10] == bytes.fromhex('a6 6a 05 01 00 2a 00 00 00 00'), request.hex()
            assert crc8(request[2:10]) == request[10], 'bad request CRC'
            response = bytearray.fromhex('5a a5 05 01 00 2a 54 50 35 01 00')
            if case == 'payload':
                response[9] ^= 1
            elif case == 'sequence':
                response[5] ^= 1
            elif case == 'version':
                response[2] ^= 1
            elif case == 'error_flag':
                response[10] = 0x80
            response.append(crc8(response[2:]))
            if case == 'crc':
                response[-1] ^= 1
            if case == 'eof':
                os.close(master)
                master = -1
            elif case == 'fragmented':
                for part in [response[:3], response[3:7], response[7:]]:
                    os.write(master, part)
                    time.sleep(0.01)
            else:
                os.write(master, response)
            stdout, stderr = proc.communicate(timeout=3)
            expected_success = case in ('valid', 'fragmented')
            assert (proc.returncode == 0) == expected_success, (case, proc.returncode, stdout, stderr)
            if expected_success:
                assert b'round-trip: PASS' in stdout, stdout
                value = re.search(rb'RTT_NS=(\d+)', stdout)
                assert value and int(value.group(1)) > 0, stdout
            else:
                assert b'round-trip: PASS' not in stdout, stdout
            print('PTY_CASE: PASS', case, flush=True)
        finally:
            if proc and proc.poll() is None:
                proc.kill()
                proc.communicate()
            if master >= 0:
                os.close(master)
            os.close(slave)
    print(f'UART_CLIENT_PTY: PASS cases={len(cases)} HARDWARE=false')


if __name__ == '__main__':
    main()
