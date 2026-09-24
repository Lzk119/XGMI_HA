# -*- coding: utf-8 -*-
"""直接向极米神灯发送一条控制指令（不经过 Home Assistant，用于排障）。

用法::

    python send_command.py 192.168.1.100 "打开日光灯"
    python send_command.py 192.168.1.100 "关灯" --listen   # 顺便监听 16751 收应答
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time

CONTROL_PORT = 16750
RESPONSE_PORT = 16751
MODE = 5
MSGID = "2"
ACTION_CONTROL = 20000
ACTION_RESPONSE = 20001


def build_payload(command: str) -> bytes:
    """打包成设备要求的 JSON 报文。"""
    return json.dumps(
        {
            "action": ACTION_CONTROL,
            "controlCmd": {
                "data": command,
                "delayTime": 0,
                "mode": MODE,
                "time": 0,
                "type": 0,
            },
            "msgid": MSGID,
        },
        ensure_ascii=False,
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="向极米神灯发送控制指令")
    parser.add_argument("host", help="设备 IP")
    parser.add_argument("command", help="指令文本，例如 打开日光灯")
    parser.add_argument(
        "--listen", action="store_true",
        help="顺带监听 %d 接收设备应答（端口被占用时会自动跳过）" % RESPONSE_PORT,
    )
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if args.listen:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", RESPONSE_PORT))
            print("已监听 0.0.0.0:%d 等待应答" % RESPONSE_PORT)
        except OSError as err:
            print("监听 %d 失败（%s），仍会发送指令" % (RESPONSE_PORT, err))
        sock.settimeout(3.0)

    payload = build_payload(args.command)
    sock.sendto(payload, (args.host, CONTROL_PORT))
    print("已发送 -> %s:%d" % (args.host, CONTROL_PORT))
    print("  %s" % payload.decode("utf-8"))
    print("  %d 字节" % len(payload))

    if args.listen:
        try:
            while True:
                data, addr = sock.recvfrom(4096)
                print("  应答 <- %s:%d  %s" % (
                    addr[0], addr[1], data.decode("utf-8", "replace")
                ))
                try:
                    if json.loads(data.decode("utf-8")).get("action") == ACTION_RESPONSE:
                        break
                except Exception:
                    continue
        except socket.timeout:
            print("  3s 内无应答。设备只把应答发到已注册的控制器，"
                  "收不到不代表指令未执行。")

    sock.close()
    time.sleep(0.1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
