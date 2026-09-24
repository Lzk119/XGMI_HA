"""极米神灯投影仪开关实体。"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_CMD_PROJECTOR_OFF, CONF_CMD_PROJECTOR_ON, DOMAIN
from .entity import XgimiLampEntity
from .runtime import XgimiLampRuntime

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置投影开关实体。"""
    runtime: XgimiLampRuntime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([XgimiProjectorSwitch(runtime)])


class XgimiProjectorSwitch(XgimiLampEntity, SwitchEntity, RestoreEntity):
    """极米神灯的投影仪开关。

    注意：投影仪开机需要数十秒，实体状态是乐观更新，并不代表投影已真正点亮。
    """

    _attr_name = "投影仪"
    _attr_icon = "mdi:projector"

    def __init__(self, runtime: XgimiLampRuntime) -> None:
        super().__init__(runtime, "projector")
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        """恢复 HA 重启前的状态。"""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == STATE_ON

    async def async_turn_on(self, **kwargs: Any) -> None:
        """打开投影仪。"""
        await self._async_send_command(self._runtime.command(CONF_CMD_PROJECTOR_ON))
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """关闭投影仪。"""
        await self._async_send_command(self._runtime.command(CONF_CMD_PROJECTOR_OFF))
        self._attr_is_on = False
        self.async_write_ha_state()
