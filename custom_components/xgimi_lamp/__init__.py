"""极米神灯 HA 自定义集成。

通过局域网 UDP 控制极米神灯的灯（日光灯 / 节律光）与投影仪开关。

协议（抓包确认）：

    控制器 -> 设备   UDP 16750
    {"action": 20000, "controlCmd": {"data": "<中文指令>", "delayTime": 0,
     "mode": 5, "time": 0, "type": 0}, "msgid": "2"}
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import ATTR_COMMAND, DOMAIN, SERVICE_SEND_COMMAND
from .protocol import XgimiUdpClient
from .runtime import XgimiLampRuntime, build_client, build_commands, build_name

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_COMMAND): cv.string,
        vol.Optional(CONF_HOST): cv.string,
        vol.Optional("wait_response", default=False): cv.boolean,
    }
)


# ---------------------------------------------------------------------------
# 运行时数据访问
# ---------------------------------------------------------------------------
def _runtimes(hass: HomeAssistant) -> dict[str, XgimiLampRuntime]:
    return hass.data.get(DOMAIN, {})


def _resolve_runtime(
    hass: HomeAssistant, host: str | None = None
) -> XgimiLampRuntime:
    """按 host 查找运行时；未指定 host 时要求只有一台设备。"""
    runtimes = _runtimes(hass)
    if not runtimes:
        raise ServiceValidationError("尚未配置任何极米神灯设备")

    if host:
        for runtime in runtimes.values():
            if runtime.host == host:
                return runtime
        raise ServiceValidationError(f"没有已配置的设备使用 IP {host}")

    if len(runtimes) > 1:
        raise ServiceValidationError(
            "配置了多台极米神灯，请用 host 字段指定目标设备"
        )
    return next(iter(runtimes.values()))


# ---------------------------------------------------------------------------
# 集成入口
# ---------------------------------------------------------------------------
async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """注册域级服务。"""
    hass.data.setdefault(DOMAIN, {})

    async def _async_handle_send_command(
        call: ServiceCall,
    ) -> ServiceResponse | None:
        """发送任意指令串（调试/验证用）。"""
        runtime = _resolve_runtime(hass, call.data.get(CONF_HOST))
        command: str = call.data[ATTR_COMMAND]

        # 调用方要响应数据时，顺带等待设备回包
        want_response: bool = call.return_response
        wait_response: bool = bool(call.data["wait_response"]) or want_response

        device_response = await runtime.client.async_send(
            command, wait_response=wait_response
        )
        _LOGGER.info("已向 %s 发送指令 %r", runtime.host, command)

        if not want_response:
            return None

        return {
            "host": runtime.host,
            "command": command,
            "local_port": runtime.client.local_port,
            "response": device_response,
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        _async_handle_send_command,
        schema=SERVICE_SEND_COMMAND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """通过 UI 配置项初始化集成。"""
    hass.data.setdefault(DOMAIN, {})

    client: XgimiUdpClient = build_client(entry)
    try:
        await client.async_start()
    except Exception:  # noqa: BLE001 - 设备离线不应导致集成加载失败
        _LOGGER.warning(
            "%s 的 UDP 通道初始化失败，将在首次下发指令时重试", entry.data[CONF_HOST]
        )

    hass.data[DOMAIN][entry.entry_id] = XgimiLampRuntime(
        entry_id=entry.entry_id,
        host=entry.data[CONF_HOST],
        name=build_name(entry),
        client=client,
        commands=build_commands(entry),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 选项变更后自动重载，让新的指令串立即生效
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载集成配置项。"""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime: XgimiLampRuntime | None = hass.data[DOMAIN].pop(entry.entry_id, None)
        if runtime is not None:
            await runtime.client.async_stop()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """选项更新后重载配置项。"""
    await hass.config_entries.async_reload(entry.entry_id)
