# -*- coding: utf-8 -*-
"""极简 pcap 解析器：提取 UDP/TCP 载荷。

不依赖 scapy / tshark，只用标准库，方便在任意机器上排查局域网协议。

用法::

    python parse_pcap.py xgimi-lan.pcap
    python parse_pcap.py xgimi-lan.pcap --port 16750
    python parse_pcap.py xgimi-lan.pcap --all      # 含 SSDP/mDNS 噪音
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
import sys

NOISE_PORTS = {1900, 5353}  # SSDP / mDNS


def iter_packets(path: str):
    """逐个产出 (序号, 相对时间, 原始帧)。"""
    with open(path, "rb") as handle:
        blob = handle.read()

    magic = struct.unpack("<I", blob[:4])[0]
    endian = "<" if magic in (0xA1B2C3D4, 0xA1B23C4D) else ">"
    nanosecond = magic in (0xA1B23C4D, 0x4D3CB2A1)

    offset = 24
    index = 0
    first: float | None = None
    while offset + 16 <= len(blob):
        ts_sec, ts_frac, incl_len, _ = struct.unpack(
            endian + "IIII", blob[offset : offset + 16]
        )
        offset += 16
        frame = blob[offset : offset + incl_len]
        offset += incl_len

        stamp = ts_sec + ts_frac / (1e9 if nanosecond else 1e6)
        if first is None:
            first = stamp
        yield index, stamp - first, frame
        index += 1


def parse_frame(frame: bytes):
    """解析以太网帧，返回 (proto, src, sport, dst, dport, payload)。"""
    if len(frame) < 14:
        return None
    ethertype = struct.unpack(">H", frame[12:14])[0]
    payload = frame[14:]

    # 处理 VLAN 标签
    while ethertype in (0x8100, 0x88A8) and len(payload) >= 4:
        ethertype = struct.unpack(">H", payload[2:4])[0]
        payload = payload[4:]

    if ethertype != 0x0800 or len(payload) < 20:
        return None

    ihl = (payload[0] & 0x0F) * 4
    proto = payload[9]
    src = socket.inet_ntoa(payload[12:16])
    dst = socket.inet_ntoa(payload[16:20])
    l4 = payload[ihl:]

    if proto == 17 and len(l4) >= 8:  # UDP
        sport, dport, ulen, _ = struct.unpack(">HHHH", l4[:8])
        body = l4[8 : ulen if ulen >= 8 else len(l4)]
        return "UDP", src, sport, dst, dport, body

    if proto == 6 and len(l4) >= 20:  # TCP
        sport, dport = struct.unpack(">HH", l4[:4])
        data_offset = (l4[12] >> 4) * 4
        return "TCP", src, sport, dst, dport, l4[data_offset:]

    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="极简 pcap 载荷提取器")
    parser.add_argument("pcap", help="pcap 文件路径")
    parser.add_argument(
        "--port", type=int, action="append", default=None,
        help="只看该端口（可重复指定）",
    )
    parser.add_argument("--all", action="store_true", help="包含 SSDP/mDNS 噪音")
    args = parser.parse_args()

    total = 0
    shown = 0
    for index, rel, frame in iter_packets(args.pcap):
        total += 1
        parsed = parse_frame(frame)
        if parsed is None:
            continue
        proto, src, sport, dst, dport, body = parsed

        if args.port:
            if not any(p in (sport, dport) for p in args.port):
                continue
        elif not args.all and (sport in NOISE_PORTS or dport in NOISE_PORTS):
            continue

        shown += 1
        print("#%-4d +%.3fs %s %s:%d -> %s:%d  len=%d" % (
            index, rel, proto, src, sport, dst, dport, len(body)
        ))
        if not body:
            print()
            continue
        try:
            print("      %s" % body.decode("utf-8"))
        except UnicodeDecodeError:
            print("      HEX %s" % body.hex())
        print()

    print("共 %d 个包，命中 %d 个" % (total, shown))

    # JSON 载荷额外做一次格式化，方便对照协议
    print("\n--- 载荷为 JSON 的包（解析后）---")
    for index, rel, frame in iter_packets(args.pcap):
        parsed = parse_frame(frame)
        if parsed is None:
            continue
        proto, src, sport, dst, dport, body = parsed
        if args.port and not any(p in (sport, dport) for p in args.port):
            continue
        if not args.port and not args.all and (sport in NOISE_PORTS or dport in NOISE_PORTS):
            continue
        try:
            message = json.loads(body.decode("utf-8").replace("'", '"'))
        except Exception:
            continue
        print("#%-4d +%.3fs %s:%d -> %s:%d" % (index, rel, src, sport, dst, dport))
        print("      %s" % json.dumps(message, ensure_ascii=False, indent=6))

    return 0


if __name__ == "__main__":
    sys.exit(main())
