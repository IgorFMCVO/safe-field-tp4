#!/usr/bin/env python3
"""Physical 1.5-Mbaud TP5 benchmark. Requires pyserial on the real Raspberry.
RAW24 bytes may coexist with replies.  No value is written unless a matching,
CRC-valid TP5 response was observed; this script is never a hardware simulator.
"""
import argparse, csv, json, statistics, time

def crc8(data):
    c=0
    for b in data:
        c ^= b
        for _ in range(8): c=((c<<1)^0x07)&0xFF if c&0x80 else (c<<1)&0xFF
    return c

def cmd_frame(cmd,seq,payload):
    b=bytearray([0xA6,0x6A,0x05,cmd,(seq>>8)&255,seq&255])
    b += int(payload & 0xffffffff).to_bytes(4,'big')
    b.append(crc8(b[2:]))
    return bytes(b)

def parse_response(frame):
    if len(frame)!=12 or frame[:3]!=bytes([0x5A,0xA5,0x05]): raise ValueError('invalid response header/length')
    if crc8(frame[2:11]) != frame[11]: raise ValueError('response crc')
    return {'type':frame[3],'sequence':int.from_bytes(frame[4:6],'big'),'data':int.from_bytes(frame[6:10],'big'),'flags':frame[10]}

def read_matching(ser, command, sequence, timeout_s=1.0):
    """Scan the 1.5-Mbaud shared stream without falling behind RAW24 traffic."""
    deadline=time.monotonic()+timeout_s; buffer=bytearray(); discarded=0; crc_errors=0
    while time.monotonic()<deadline:
        waiting=getattr(ser,'in_waiting',0)
        chunk=ser.read(max(1,min(65536,waiting or 1)))
        if not chunk: continue
        buffer.extend(chunk)
        while True:
            start=buffer.find(b'\x5a\xa5')
            if start<0:
                # Retain one possible 0x5a prefix across reads.
                keep=1 if buffer and buffer[-1]==0x5a else 0
                discarded+=len(buffer)-keep
                if keep: buffer[:]=buffer[-1:]
                else: buffer.clear()
                break
            discarded+=start
            if start: del buffer[:start]
            if len(buffer)<12: break
            frame=bytes(buffer[:12])
            try:
                p=parse_response(frame)
                del buffer[:12]
                if p['type']==command and p['sequence']==sequence:
                    return p,discarded,crc_errors
                discarded+=12
            except ValueError:
                # False preamble inside RAW24: advance by one to preserve any
                # overlapping real response sync and continue bulk scanning.
                crc_errors+=1;discarded+=1;del buffer[0]
    raise TimeoutError('matching TP5 response not received')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--device',default='/dev/serial0'); ap.add_argument('--count',type=int,default=100); ap.add_argument('--baud',type=int,default=1500000); ap.add_argument('--out-prefix',default='build/tp5_uart_perf'); args=ap.parse_args()
    try: import serial
    except ImportError: raise SystemExit('pyserial is required only for this physical benchmark')
    ser=serial.Serial(args.device,args.baud,timeout=0.05)
    rows=[]; failures=0
    for i in range(args.count):
        seq=i & 0xffff; f=cmd_frame(0x01,seq,0)
        t0=time.perf_counter_ns(); ser.write(f); ser.flush()
        try:
            p,discarded,crc_recovered=read_matching(ser,1,seq); ok=p['data']==0x54503501 and not (p['flags']&0x80)
        except Exception: ok=False; discarded=0; crc_recovered=0
        t1=time.perf_counter_ns()
        failures += 0 if ok else 1
        rows.append({'sequence':seq,'rtt_us':(t1-t0)/1000.0,'ok':int(ok),'discarded_bytes':discarded,'recovered_crc_frames':crc_recovered})
    ser.close()
    okr=[x['rtt_us'] for x in rows if x['ok']]
    summary={'hardware':True,'baud':args.baud,'count':args.count,'pass':len(okr),'fail':failures,'mean_rtt_us':statistics.mean(okr) if okr else None,'median_rtt_us':statistics.median(okr) if okr else None,'p95_rtt_us':sorted(okr)[max(0,int(len(okr)*0.95)-1)] if okr else None,'throughput_commands_s':(1_000_000/statistics.mean(okr)) if okr else None,'raw24_bytes_discarded':sum(x['discarded_bytes'] for x in rows),'crc_frames_recovered':sum(x['recovered_crc_frames'] for x in rows)}
    import pathlib; pathlib.Path(args.out_prefix).parent.mkdir(parents=True,exist_ok=True)
    with open(args.out_prefix+'.csv','w',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
    with open(args.out_prefix+'.json','w') as fh: json.dump(summary,fh,indent=2)
    print(json.dumps(summary,indent=2)); raise SystemExit(0 if failures==0 else 1)
if __name__=='__main__': main()
