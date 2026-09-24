"""实体公共基类：统一设备信息与运行时访问。"""

from __future__ import annotations

import logging

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .runtime import XgimiLampRuntime

_LOGGER = logging.getLogger(__name__)


class XgimiLampEntity(Entity):
    """极米神灯实体基类。"""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, runtime: XgimiLampRuntime, unique_suffix: str) -> None:
        self._runtime = runtime
        self._attr_unique_id = f"{runtime.entry_id}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.entry_id)},
            name=runtime.name,
            manufacturer="极米 XGIMI",
            model="神灯",
        )

    async def _async_send_command(self, command: str) -> None:
        """发送指令；失败只记日志，不抛异常（设备离线时 HA 不应报错）。"""
        try:
            await self._runtime.client.async_send(command)
        except Exception:  # noqa: BLE001 - 通信层任何异常都不应打断实体
            _LOGGER.exception("向 %s 发送指令 %r 失败", self._runtime.host, command)
