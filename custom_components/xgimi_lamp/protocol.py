"""极米神灯的 UDP 通信客户端。

只依赖标准库：设备不要求握手、不要求认证，控制器把一条 JSON 丢到设备的
UDP 16750 即可。设备会把结果（``action: 20001``）回发到控制器的
UDP 16751，因此这里优先把本地 socket 绑在 16751 上，以便拿到回包做诊断。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .const import (
    ACTION_CONTROL,
    ACTION_RESPONSE,
    COMMAND_TIMEOUT,
    CONTROL_PORT,
    DEFAULT_MODE,
    DEFAULT_MSGID,
    RESPONSE_PORT,
)

_LOGGER = logging.getLogger(__name__)


class XgimiError(Exception):
    """极米通信异常基类。"""


class XgimiConnectionError(XgimiError):
    """无法建立本地 UDP 通道。"""


class XgimiUdpClient:
    """与单台极米神灯通信的 UDP 客户端。

    生命周期跟随 config entry：``async_start()`` 建立长连接，
    ``async_stop()`` 关闭。指令可"发后不理"，也可等待设备回包。
    """

    def __init__(
        self,
        host: str,
        *,
        control_port: int = CONTROL_PORT,
        response_port: int = RESPONSE_PORT,
        mode: int = DEFAULT_MODE,
        msgid: str = DEFAULT_MSGID,
    ) -> None:
        self.host = host
        self.control_port = control_port
        self.response_port = response_port
        self.mode = mode
        self.msgid = msgid

        self._transport: asyncio.DatagramTransport | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()
        self._local_port: int | None = None
        self.last_response: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------
    @property
    def local_port(self) -> int | None:
        """本地实际绑定的端口（16751 表示能收到设备回包）。"""
        return self._local_port

    @property
    def connected(self) -> bool:
        """本地 UDP 通道是否已就绪。"""
        return self._transport is not None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    async def async_start(self) -> None:
        """建立 UDP 通道（幂等）。"""
        if self._transport is not None:
            return

        loop = asyncio.get_running_loop()
        # 优先绑定 16751（设备的回包目标端口）；若被官方 App 等占用则退回随机端口
        for port in (self.response_port, 0):
            try:
                transport, _ = await loop.create_datagram_endpoint(
                    lambda: _XgimiDatagramProtocol(self),
                    local_addr=("0.0.0.0", port),
                    remote_addr=(self.host, self.control_port),
                )
            except OSError as err:
                _LOGGER.debug("绑定本地 UDP 端口 %s 失败：%s", port, err)
                continue

            self._transport = transport  # type: ignore[assignment]
            self._local_port = port or transport.get_extra_info("sockname")[1]
            if port:
                _LOGGER.debug(
                    "UDP 通道就绪：本地 %s -> %s:%s（可接收设备回包）",
                    self._local_port,
                    self.host,
                    self.control_port,
                )
            else:
                _LOGGER.debug(
                    "UDP 通道就绪：本地 %s（随机端口）-> %s:%s，"
                    "端口 %s 被占用，将收不到设备回包",
                    self._local_port,
                    self.host,
                    self.control_port,
                    self.response_port,
                )
            return

        raise XgimiConnectionError(
            f"无法为 {self.host} 创建本地 UDP 通道（{self.response_port} 与随机端口均失败）"
        )

    async def async_stop(self) -> None:
        """关闭 UDP 通道并清理等待中的请求。"""
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()
        self._local_port = None

    # ------------------------------------------------------------------
    # 发送
    # ------------------------------------------------------------------
    def build_payload(self, command: str) -> bytes:
        """把中文指令串打包成设备要求的 JSON 报文。"""
        payload = {
            "action": ACTION_CONTROL,
            "controlCmd": {
                "data": command,
                "delayTime": 0,
                "mode": self.mode,
                "time": 0,
                "type": 0,
            },
            "msgid": self.msgid,
        }
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    async def async_send(
        self,
        command: str,
        *,
        wait_response: bool = False,
        timeout: float = COMMAND_TIMEOUT,
    ) -> dict[str, Any] | None:
        """向设备发送一条控制指令。

        :param command: 中文指令串，例如"打开日光灯"
        :param wait_response: 是否等待设备回包（回包仅用于诊断）
        :param timeout: 等待回包的超时时间
        :return: 设备回包解析结果；未等待或超时则返回 ``None``
        """
        async with self._lock:
            await self.async_start()
            assert self._transport is not None

            future: asyncio.Future[dict[str, Any]] | None = None
            if wait_response:
                future = asyncio.get_running_loop().create_future()
                self._pending[self.msgid] = future

            try:
                self._transport.sendto(self.build_payload(command))
            except OSError as err:
                if future is not None:
                    self._pending.pop(self.msgid, None)
                raise XgimiError(f"发送指令 {command!r} 失败：{err}") from err

            _LOGGER.debug("已向 %s:%s 发送指令 %r", self.host, self.control_port, command)

            if future is None:
                return None

            try:
                return await asyncio.wait_for(future, timeout)
            except (asyncio.TimeoutError, TimeoutError):
                _LOGGER.debug("指令 %r 在 %.1fs 内未收到设备回包", command, timeout)
                return None
            finally:
                self._pending.pop(self.msgid, None)

    # ------------------------------------------------------------------
    # 接收
    # ------------------------------------------------------------------
    def _handle_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        """处理设备回包。"""
        try:
            message = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _LOGGER.debug("收到非 JSON 回包（%s）：%r", addr, data)
            return

        if not isinstance(message, dict):
            _LOGGER.debug("收到非预期回包（%s）：%r", addr, message)
            return

        if message.get("action") != ACTION_RESPONSE:
            _LOGGER.debug("忽略未知 action 的回包（%s）：%s", addr, message)
            return

        _LOGGER.debug("收到设备回包：%s", message)
        self.last_response = message

        future = self._pending.get(str(message.get("msgid", "")))
        if future is not None and not future.done():
            future.set_result(message)


class _XgimiDatagramProtocol(asyncio.DatagramProtocol):
    """把收到的数据转交给客户端。"""

    def __init__(self, client: XgimiUdpClient) -> None:
        self._client = client

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._client._handle_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:
        # UDP 是"发后不理"的，设备不在线时这里会收到 ICMP 端口不可达
        _LOGGER.debug("UDP 通信错误（设备可能不在线）：%s", exc)
