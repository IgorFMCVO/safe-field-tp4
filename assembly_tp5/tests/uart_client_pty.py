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
    cases = ['valid', 'raw24_interleaved', 'fragmented', 'crc_recovery', 'payload', 'error_flag', 'eof']
    for case in cases:
        master, slave = pty.openpty()
        proc = None
        try:
            tty.setraw(slave)
            proc = subprocess.Popen(shlex.split(args.runner) + [str(Path(args.binary).resolve()), os.ttyname(slave)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            commands = [(1, 0x2a, 0, 0x54503501),
                        (0x10, 0x2b, 0x40004000, 0x2000),
                        (0x10, 0x2c, 0x80008000, 0x8000),
                        (0x11, 0x2d, 0x3e004000, 0x4200)]
            for n, (cmd, seq, payload, expected) in enumerate(commands):
                request = read_exact(master, 11)
                prefix = bytes([0xa6, 0x6a, 5, cmd, seq >> 8, seq & 255]) + payload.to_bytes(4, 'big')
                assert request[:10] == prefix, request.hex()
                assert crc8(request[2:10]) == request[10], 'bad request CRC'
                response = bytearray([0x5a, 0xa5, 5, cmd, seq >> 8, seq & 255]) + expected.to_bytes(4, 'big') + bytearray([0])
                if case == 'payload' and n == 0:
                    response[9] ^= 1
                elif case == 'error_flag' and n == 0:
                    response[10] = 0x80
                response.append(crc8(response[2:]))
                if case == 'eof' and n == 0:
                    os.close(master); master = -1; break
                if case == 'raw24_interleaved':
                    # Deliberately contains a false response preamble followed by
                    # non-TP5 bytes; parser must recover and match its sequence.
                    os.write(master, b'RAW24\x5a\xa5\x99\x00\x11\x22\x33\x44\x55\x66\x77\x88')
                if case == 'crc_recovery' and n == 0:
                    bad = bytearray(response); bad[-1] ^= 1; os.write(master, bad)
                if case == 'fragmented':
                    for part in [response[:3], response[3:7], response[7:]]:
                        os.write(master, part); time.sleep(0.01)
                else:
                    os.write(master, response)
                if case in ('payload', 'error_flag', 'eof'):
                    break
            stdout, stderr = proc.communicate(timeout=3)
            expected_success = case in ('valid', 'raw24_interleaved', 'fragmented', 'crc_recovery')
            assert (proc.returncode == 0) == expected_success, (case, proc.returncode, stdout, stderr)
            if expected_success:
                assert b'round-trip: PASS' in stdout, stdout
                value = re.search(rb'RTT_NS=(\d+)', stdout)
                assert value and int(value.group(1)) > 0, stdout
                assert b'COMMANDS_VERIFIED=4' in stdout, stdout
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
