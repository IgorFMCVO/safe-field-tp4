#!/usr/bin/env python3
from safe_field_bidirectional_test import command_packet, crc8


def main() -> int:
    vectors = [(1, 0x3001, 123), (1, 0x3002, -123), (1, 0x3003, 32767)]
    for command, sequence, payload in vectors:
        packet = command_packet(command, sequence, payload)
        assert len(packet) == 11
        assert packet[:2] == b"\xA6\x6A"
        assert crc8(packet[2:10]) == packet[10]
        print(f"seq={sequence} payload={payload} packet={packet.hex()} PASS")
    print("TEST_RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
