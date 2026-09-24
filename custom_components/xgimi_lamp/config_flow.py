"""极米神灯配置流程。

包含两个流程：

* ``user``：添加设备时填写 IP 与名称
* ``init``（选项）：选择灯实体形态、默认开灯模式，并自定义五条控制指令串
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

try:  # HA >= 2024.4
    from homeassistant.config_entries import ConfigFlowResult
except ImportError:  # pragma: no cover - 兼容旧版 HA
    from typing import Any as _Any

    ConfigFlowResult = dict[str, _Any]  # type: ignore[misc,assignment]

from .const import (
    CONF_CMD_LIGHT_DAYLIGHT,
    CONF_CMD_LIGHT_OFF,
    CONF_CMD_LIGHT_RHYTHM,
    CONF_CMD_PROJECTOR_OFF,
    CONF_CMD_PROJECTOR_ON,
    CONF_DEFAULT_LIGHT_MODE,
    CONF_LIGHT_SHAPE,
    DEFAULT_COMMANDS,
    DEFAULT_LIGHT_MODE,
    DEFAULT_LIGHT_SHAPE,
    DEFAULT_NAME,
    DOMAIN,
    LIGHT_MODES,
    LIGHT_SHAPE_SINGLE,
    LIGHT_SHAPE_SPLIT,
)

_LOGGER = logging.getLogger(__name__)

# 需要校验非空的指令串配置项
COMMAND_KEYS = tuple(DEFAULT_COMMANDS)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
    }
)

SHAPE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(
                value=LIGHT_SHAPE_SPLIT,
                label="分开：日光灯 / 节律灯 / 投影（3 个实体）",
            ),
            selector.SelectOptionDict(
                value=LIGHT_SHAPE_SINGLE,
                label="单灯体：灯（可切换模式）/ 投影（2 个实体）",
            ),
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)

LIGHT_MODE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=list(LIGHT_MODES),
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)


class XgimiLampConfigFlow(ConfigFlow, domain=DOMAIN):
    """极米神灯配置流程。"""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """用户输入步骤：填写设备 IP 和名称。"""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = (user_input.get(CONF_HOST) or "").strip()
            name = (user_input.get(CONF_NAME) or "").strip() or DEFAULT_NAME

            if not host:
                errors[CONF_HOST] = "invalid_host"
            else:
                # 以 host 作为唯一标识，防止重复添加
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=name,
                    data={CONF_HOST: host, CONF_NAME: name},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """返回选项流程。"""
        return XgimiLampOptionsFlow()


class XgimiLampOptionsFlow(OptionsFlow):
    """选项：实体形态 + 五条控制指令串。

    极米不同机型/固件的指令文本可能略有差异，因此全部做成可配置项，
    配合 ``xgimi_lamp.send_command`` 服务可以在不重启 HA 的情况下试出正确值。
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """选项表单。"""
        errors: dict[str, str] = {}

        if user_input is not None:
            cleaned: dict[str, Any] = dict(user_input)
            for key in COMMAND_KEYS:
                cleaned[key] = str(cleaned.get(key, "")).strip()
            if any(not cleaned[key] for key in COMMAND_KEYS):
                errors["base"] = "empty_command"
            else:
                return self.async_create_entry(title="", data=cleaned)

        current = dict(DEFAULT_COMMANDS)
        current.update(
            {
                key: value
                for key, value in self.config_entry.options.items()
                if key in DEFAULT_COMMANDS
            }
        )

        shape = self.config_entry.options.get(CONF_LIGHT_SHAPE, DEFAULT_LIGHT_SHAPE)
        if shape not in (LIGHT_SHAPE_SPLIT, LIGHT_SHAPE_SINGLE):
            shape = DEFAULT_LIGHT_SHAPE

        default_mode = self.config_entry.options.get(
            CONF_DEFAULT_LIGHT_MODE, DEFAULT_LIGHT_MODE
        )
        if default_mode not in LIGHT_MODES:
            default_mode = DEFAULT_LIGHT_MODE

        schema = vol.Schema(
            {
                vol.Required(CONF_LIGHT_SHAPE, default=shape): SHAPE_SELECTOR,
                vol.Required(
                    CONF_DEFAULT_LIGHT_MODE, default=default_mode
                ): LIGHT_MODE_SELECTOR,
                vol.Required(
                    CONF_CMD_LIGHT_DAYLIGHT,
                    default=current[CONF_CMD_LIGHT_DAYLIGHT],
                ): str,
                vol.Required(
                    CONF_CMD_LIGHT_RHYTHM,
                    default=current[CONF_CMD_LIGHT_RHYTHM],
                ): str,
                vol.Required(
                    CONF_CMD_LIGHT_OFF,
                    default=current[CONF_CMD_LIGHT_OFF],
                ): str,
                vol.Required(
                    CONF_CMD_PROJECTOR_ON,
                    default=current[CONF_CMD_PROJECTOR_ON],
                ): str,
                vol.Required(
                    CONF_CMD_PROJECTOR_OFF,
                    default=current[CONF_CMD_PROJECTOR_OFF],
                ): str,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={"host": self.config_entry.data[CONF_HOST]},
        )
