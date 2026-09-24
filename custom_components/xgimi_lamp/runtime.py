"""运行时数据：把 config entry 解析成实体可直接使用的对象。"""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME

from .const import (
    CONF_HOST,
    DEFAULT_COMMANDS,
    DEFAULT_NAME,
)
from .protocol import XgimiUdpClient


def build_commands(entry: ConfigEntry) -> dict[str, str]:
    """合并默认指令串与用户在选项里覆盖的值。"""
    commands = dict(DEFAULT_COMMANDS)
    for key in commands:
        value = entry.options.get(key)
        if isinstance(value, str) and value.strip():
            commands[key] = value.strip()
    return commands


def build_client(entry: ConfigEntry) -> XgimiUdpClient:
    """根据 config entry 创建 UDP 客户端。"""
    return XgimiUdpClient(entry.data[CONF_HOST])


def build_name(entry: ConfigEntry) -> str:
    """设备显示名。"""
    return entry.data.get(CONF_NAME) or DEFAULT_NAME


@dataclass(slots=True)
class XgimiLampRuntime:
    """单个 config entry 的运行时上下文。"""

    entry_id: str
    host: str
    name: str
    client: XgimiUdpClient
    commands: dict[str, str] = field(default_factory=dict)

    def command(self, key: str) -> str:
        """按配置项 key 取指令串。"""
        return self.commands[key]
