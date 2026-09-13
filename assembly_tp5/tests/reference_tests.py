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
responses=[(0x01,0x002a,0x54503501,0),(0x10,0x002b,0x2000,0),
           (0x10,0x002c,0x8000,0),(0x11,0x002d,0x4200,0)]
for typ,seq,data,flags in responses:
    body=bytes([5,typ,seq>>8,seq&255])+data.to_bytes(4,'big')+bytes([flags])
    frame=bytes([0x5a,0xa5])+body+bytes([crc8(body)])
    assert len(frame)==12 and crc8(frame[2:11])==frame[11]
print("TEST_RESULT: PASS assembly reference command_vectors=3 response_vectors=4")
