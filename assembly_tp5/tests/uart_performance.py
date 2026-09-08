#!/usr/bin/env python3
"""Physical UART benchmark for TP5. Requires pyserial only on Raspberry.
It never fabricates results; writes CSV/JSON only from frames actually received.
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

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--device',default='/dev/serial0'); ap.add_argument('--count',type=int,default=100); ap.add_argument('--out-prefix',default='build/tp5_uart_perf'); args=ap.parse_args()
    try: import serial
    except ImportError: raise SystemExit('pyserial is required only for this physical benchmark')
    ser=serial.Serial(args.device,115200,timeout=1)
    rows=[]; failures=0
    for i in range(args.count):
        seq=i & 0xffff; f=cmd_frame(0x01,seq,0)
        t0=time.perf_counter_ns(); ser.write(f); ser.flush(); r=ser.read(12); t1=time.perf_counter_ns()
        try:
            p=parse_response(r); ok=p['sequence']==seq and p['type']==1 and p['data']==0x54503501
        except Exception: ok=False
        failures += 0 if ok else 1
        rows.append({'sequence':seq,'rtt_us':(t1-t0)/1000.0,'ok':int(ok),'rx_len':len(r)})
    ser.close()
    okr=[x['rtt_us'] for x in rows if x['ok']]
    summary={'count':args.count,'pass':len(okr),'fail':failures,'mean_rtt_us':statistics.mean(okr) if okr else None,'median_rtt_us':statistics.median(okr) if okr else None,'p95_rtt_us':sorted(okr)[max(0,int(len(okr)*0.95)-1)] if okr else None,'throughput_commands_s':(1_000_000/statistics.mean(okr)) if okr else None}
    import pathlib; pathlib.Path(args.out_prefix).parent.mkdir(parents=True,exist_ok=True)
    with open(args.out_prefix+'.csv','w',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
    with open(args.out_prefix+'.json','w') as fh: json.dump(summary,fh,indent=2)
    print(json.dumps(summary,indent=2)); raise SystemExit(0 if failures==0 else 1)
if __name__=='__main__': main()
