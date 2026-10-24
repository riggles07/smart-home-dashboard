"""ICMP reachability probe (no `ping` binary in this container).

Confirms whether the wall panel's tailnet address is actually answering at the IP
layer. That separates "panel is offline / not on the tailnet" from "panel is up but
its MQTT client is misaddressed" -- the two remain possible causes of the broker
seeing nothing from 100.92.176.5.
"""
import os
import socket
import struct
import sys
import time


def checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    s = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    s = (s >> 16) + (s & 0xFFFF)
    s += s >> 16
    return ~s & 0xFFFF


def ping(host: str, timeout: float = 3.0) -> str:
    try:
        addr = socket.gethostbyname(host)
    except Exception as e:
        return f"resolve failed ({type(e).__name__})"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    except PermissionError:
        return "no CAP_NET_RAW (cannot send ICMP from this container)"
    s.settimeout(timeout)
    pkt_id = os.getpid() & 0xFFFF
    payload = b"hermes-probe"
    hdr = struct.pack("!BBHHH", 8, 0, 0, pkt_id, 1)
    pkt = struct.pack("!BBHHH", 8, 0, checksum(hdr + payload), pkt_id, 1) + payload
    t0 = time.time()
    try:
        s.sendto(pkt, (addr, 0))
        while True:
            data, peer = s.recvfrom(1024)
            if peer[0] not in (addr,):
                continue
            ihl = (data[0] & 0x0F) * 4
            icmp = data[ihl:]
            typ, code = icmp[0], icmp[1]
            if typ == 0:
                return f"REPLY in {(time.time() - t0) * 1000:.0f} ms"
            return f"ICMP type={typ} code={code}"
    except socket.timeout:
        return "no reply (timed out)"
    except Exception as e:
        return f"error {type(e).__name__}: {e}"
    finally:
        s.close()


for host, label in (("100.92.176.5", "wall panel"),
                     ("100.104.204.118", "HA host (self, control)")):
    print(f"  {host:<16} {label:<24} {ping(host)}")
