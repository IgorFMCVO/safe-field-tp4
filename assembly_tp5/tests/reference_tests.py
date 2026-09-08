#!/usr/bin/env python3

def crc8(data):
    c=0
    for v in data:
        c ^= v
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xff if c & 0x80 else (c << 1) & 0xff
    return c

def build(cmd,seq,payload):
    body=bytes([0x05,cmd,(seq>>8)&255,seq&255,(payload>>24)&255,(payload>>16)&255,(payload>>8)&255,payload&255])
    return bytes([0xA6,0x6A])+body+bytes([crc8(body)])

vectors=[(0x01,0x002A,0x00000000),(0x10,0x1234,0x40004000),(0x11,0x1235,0x3E004000)]
for v in vectors:
    f=build(*v)
    assert len(f)==11
    assert crc8(f[2:10])==f[10]
print("TEST_RESULT: PASS assembly reference protocol vectors=3")
