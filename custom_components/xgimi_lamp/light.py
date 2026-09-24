"""极米神灯灯光实体。

灯有两种模式：日光灯、节律光。提供两种实体形态（在"配置 -> 选项"里切换）：

* ``split``（默认）：日光灯 / 节律灯 各一个开关实体，点一下就能切，不需要
  展开"更多信息"面板。
* ``single``：一个灯实体，用 ``effect`` 下拉在两种模式间切换；直接点开灯时
  使用选项里的"默认模式"。

注意：``effect`` 下拉要能显示，必须同时声明 ``LightEntityFeature.EFFECT``
特性位——只设 ``effect_list`` 是不够的。

设备不提供状态查询接口，因此状态为乐观更新，并通过 RestoreEntity
在 HA 重启后恢复上次状态。
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_EFFECT,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_CMD_LIGHT_OFF,
    CONF_DEFAULT_LIGHT_MODE,
    CONF_LIGHT_SHAPE,
    DEFAULT_LIGHT_MODE,
    DEFAULT_LIGHT_SHAPE,
    DOMAIN,
    LIGHT_MODES,
    LIGHT_MODE_TO_CONF,
    LIGHT_MODE_TO_UNIQUE,
    LIGHT_SHAPE_SINGLE,
)
from .entity import XgimiLampEntity
from .runtime import XgimiLampRuntime

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """按选项里的"实体形态"创建灯实体。"""
    runtime: XgimiLampRuntime = hass.data[DOMAIN][entry.entry_id]
    shape = entry.options.get(CONF_LIGHT_SHAPE, DEFAULT_LIGHT_SHAPE)

    if shape == LIGHT_SHAPE_SINGLE:
        default_mode = entry.options.get(CONF_DEFAULT_LIGHT_MODE, DEFAULT_LIGHT_MODE)
        if default_mode not in LIGHT_MODES:
            default_mode = DEFAULT_LIGHT_MODE
        async_add_entities([XgimiLampLight(runtime, default_mode)])
        return

    # 默认 / split / 任何无法识别的取值，一律按"分开"处理
    group = _LampGroup()
    entities: list[_XgimiLampLightBase] = [
        XgimiLampModeLight(runtime, mode, group) for mode in LIGHT_MODES
    ]
    for entity in entities:
        group.register(entity)
    async_add_entities(entities)


class _LampGroup:
    """分开形态下多个灯实体之间的状态同步。

    一台神灯只有一个灯，所以任一"模式"实体被点亮后，其余实体都应显示为关闭；
    任一实体被关闭后，其余实体同样归零。这样多个开关之间不会出现"两个都亮"的
    假状态。
    """

    def __init__(self) -> None:
        self._entities: list[XgimiLampModeLight] = []

    def register(self, entity: "XgimiLampModeLight") -> None:
        """登记一个灯实体。"""
        self._entities.append(entity)

    def sync(self, source: "XgimiLampModeLight") -> None:
        """把一个实体的状态变化同步给同组的其他实体。"""
        for entity in self._entities:
            if entity is source:
                continue
            entity.force_off()


class _XgimiLampLightBase(XgimiLampEntity, LightEntity, RestoreEntity):
    """灯实体公共部分。"""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, runtime: XgimiLampRuntime, unique_suffix: str) -> None:
        super().__init__(runtime, unique_suffix)
        self._attr_is_on = False

    @callback
    def force_off(self) -> None:
        """被同组实体抢占时强制置为关闭（不发送指令）。"""
        if not self._attr_is_on:
            return
        self._attr_is_on = False
        if self.hass is not None:
            self.async_write_ha_state()

    async def _async_apply_mode(self, mode: str) -> None:
        """发送"打开指定模式"指令并乐观置为开启。"""
        await self._async_send_command(self._runtime.command(LIGHT_MODE_TO_CONF[mode]))
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """关灯。"""
        await self._async_send_command(self._runtime.command(CONF_CMD_LIGHT_OFF))
        self._attr_is_on = False
        self.async_write_ha_state()


class XgimiLampLight(_XgimiLampLightBase):
    """单灯体形态：一个灯实体，用 effect 在日光灯 / 节律光之间切换。"""

    _attr_name = None  # 作为设备主实体，直接使用设备名
    _attr_effect_list = list(LIGHT_MODES)
    # 关键：缺少这一行，HA 前端不会显示 effect 下拉框
    _attr_supported_features = LightEntityFeature.EFFECT

    def __init__(self, runtime: XgimiLampRuntime, default_mode: str) -> None:
        super().__init__(runtime, "light")
        self._default_mode = default_mode
        self._attr_effect = default_mode

    async def async_added_to_hass(self) -> None:
        """恢复 HA 重启前的开关与模式。"""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        self._attr_is_on = last_state.state == STATE_ON
        last_effect = last_state.attributes.get(ATTR_EFFECT)
        if last_effect in LIGHT_MODES:
            self._attr_effect = last_effect

    async def async_turn_on(self, **kwargs: Any) -> None:
        """开灯：带 effect 就按 effect，否则用选项里的默认模式。"""
        effect = kwargs.get(ATTR_EFFECT)
        if effect in LIGHT_MODES:
            self._attr_effect = effect
        elif self._attr_effect not in LIGHT_MODES:
            self._attr_effect = self._default_mode

        await self._async_apply_mode(self._attr_effect)


class XgimiLampModeLight(_XgimiLampLightBase):
    """分开形态：一个实体固定对应一种灯模式，开/关即切换。"""

    def __init__(
        self, runtime: XgimiLampRuntime, mode: str, group: _LampGroup
    ) -> None:
        super().__init__(runtime, LIGHT_MODE_TO_UNIQUE[mode])
        self._mode = mode
        self._group = group
        self._attr_name = mode

    async def async_added_to_hass(self) -> None:
        """恢复状态；若恢复为开启，则把同组其他实体压回关闭。"""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == STATE_ON
        if self._attr_is_on:
            self._group.sync(self)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """打开当前实体对应的灯模式。"""
        await self._async_apply_mode(self._mode)
        self._group.sync(self)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """关灯，并让同组其他模式同步熄灭。"""
        await super().async_turn_off(**kwargs)
        self._group.sync(self)
