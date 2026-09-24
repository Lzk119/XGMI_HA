"""为 HA 自定义集成提供最小 homeassistant 桩，便于在没装 HA 的机器上跑实体逻辑测试。

用法::

    import sys
    sys.path.insert(0, r"<repo_root>")
    from ha_stub import install, check, StubState, FakeRuntime  # 视需要

    install()                       # 必须在 import 组件之前调用
    from custom_components.mydomain import light as light_mod

    async def main():
        rt = FakeRuntime({"cmd_on": "打开", "cmd_off": "关闭"})
        ent = light_mod.MyLight(rt)
        ent.hass = object()          # 模拟"已加入 HA"
        await ent.async_added_to_hass()
        await ent.async_turn_on()
        check("发出的指令正确", rt.client.sent[-1] == "打开")

    import asyncio; asyncio.run(main())

需要补别的平台（sensor/fan/climate…）时，在 install() 之后用
`mod("homeassistant.components.sensor", SensorEntity=...)` 追加即可，
或者直接改本文件。
"""

from __future__ import annotations

import sys
import types


# ---------------------------------------------------------------------------
# 基础
# ---------------------------------------------------------------------------
def mod(name: str, **attrs):
    """把一个假模块塞进 sys.modules。"""
    m = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(m, key, value)
    sys.modules[name] = m
    return m


def check(label: str, condition: bool, detail: str = "") -> None:
    """打印一条断言结果；失败则抛异常（不吞错误）。"""
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {label}{(' -> ' + detail) if detail else ''}")
    if not condition:
        raise AssertionError(label)


# ---------------------------------------------------------------------------
# 供测试注入的假对象
# ---------------------------------------------------------------------------
class StubState:
    """假的 RestoreEntity 上一次状态。"""

    def __init__(self, state: str, attributes: dict | None = None) -> None:
        self.state = state
        self.attributes = attributes or {}


class StubEntity:
    """最小实体基类。

    ``async_write_ha_state`` 会在未加入 HA 时抛异常 —— 故意保留这个约束，
    这样"实体还没 add 就写状态"的 bug 能被测出来。
    """

    hass = None
    _attr_unique_id = None
    _attr_has_entity_name = False
    _attr_should_poll = True
    _attr_name = None
    _attr_device_info = None
    _attr_icon = None
    _attr_available = True
    _stub_last_state = None
    # 注意：必须是类属性。真实集成的实体基类往往不调用 super().__init__()，
    # 写成实例属性会 AttributeError。
    write_count = 0

    def async_write_ha_state(self) -> None:
        """记录一次状态写入。"""
        if self.hass is None:
            raise RuntimeError("实体尚未加入 hass，不能写状态")
        self.write_count += 1

    def async_on_remove(self, func) -> None:
        """真实 HA 里用于注册清理回调，这里直接忽略。"""

    async def async_added_to_hass(self) -> None:
        """真实 HA 由框架调用。"""

    async def async_will_remove_from_hass(self) -> None:
        """真实 HA 由框架调用。"""

    async def async_get_last_state(self):
        """返回注入的假状态，用于验证 RestoreEntity 恢复逻辑。"""
        return self._stub_last_state


class StubRuntime:
    """假的 config entry 运行时对象：记录发出去的每一条指令。"""

    class _Client:
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.local_port = 16751

        async def async_send(self, command: str, wait_response: bool = False):
            self.sent.append(command)
            return None

    def __init__(self, commands: dict[str, str] | None = None) -> None:
        self.entry_id = "entry1"
        self.host = "192.168.1.100"
        self.name = "测试设备"
        self.client = self._Client()
        self.commands = dict(commands or {})

    def command(self, key: str) -> str:
        return self.commands[key]


# 兼容别名
FakeRuntime = StubRuntime


class StubEntry:
    """假的 config entry。"""

    def __init__(self, options: dict | None = None, data: dict | None = None) -> None:
        self.entry_id = "entry1"
        self.options = dict(options or {})
        self.data = dict(data or {"host": "192.168.1.100"})


class StubHass:
    """假的 HomeAssistant，只带 data 字典。"""

    def __init__(self, domain: str | None = None, runtime=None) -> None:
        self.data: dict = {}
        if domain and runtime is not None:
            self.data[domain] = {runtime.entry_id: runtime}
        self.services = mod("homeassistant.core._services_stub",
                            async_register=lambda *a, **kw: None)


# ---------------------------------------------------------------------------
# 安装
# ---------------------------------------------------------------------------
def install(*, extra_entity_attrs: dict | None = None) -> None:
    """把所有需要的假模块装进 sys.modules。必须在 import 组件之前调用。"""
    # voluptuous
    class _Marker:
        def __init__(self, key, default=None):
            self.key = key
            self.default = default

        def __hash__(self):
            return hash(str(self.key))

        def __eq__(self, other):
            return isinstance(other, _Marker) and other.key == self.key

    vol = types.ModuleType("voluptuous")
    vol.Schema = lambda schema: schema
    vol.Required = lambda key, default=None, **kw: _Marker(key, default)
    vol.Optional = lambda key, default=None, **kw: _Marker(key, default)
    vol.In = lambda container, **kw: container
    vol.All = lambda *a, **kw: a[0] if a else None
    vol.Coerce = lambda t: t
    sys.modules["voluptuous"] = vol

    # 包
    mod("homeassistant")
    mod("homeassistant.components")
    mod("homeassistant.helpers")

    # const
    mod(
        "homeassistant.const",
        CONF_HOST="host",
        CONF_NAME="name",
        CONF_UNIQUE_ID="unique_id",
        STATE_ON="on",
        STATE_OFF="off",
        STATE_UNKNOWN="unknown",
        STATE_UNAVAILABLE="unavailable",
        Platform=type("Platform", (), {"LIGHT": "light", "SWITCH": "switch"}),
    )

    # core
    class _SupportsResponse:
        NONE = "none"
        OPTIONAL = "optional"
        ONLY = "only"

    mod(
        "homeassistant.core",
        HomeAssistant=type("HomeAssistant", (), {}),
        ServiceCall=type("ServiceCall", (), {}),
        ServiceResponse=dict,
        SupportsResponse=_SupportsResponse,
        callback=lambda func: func,
    )

    # config_entries
    class _StubFlow:
        def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

        def async_create_entry(self, **kwargs):
            return {"type": "create_entry", **kwargs}

        def async_abort(self, **kwargs):
            return {"type": "abort", **kwargs}

    mod(
        "homeassistant.config_entries",
        ConfigEntry=type("ConfigEntry", (), {}),
        ConfigFlowResult=dict,
        ConfigFlow=type(
            "ConfigFlow",
            (_StubFlow,),
            {
                # 真实集成写成 class XxxFlow(ConfigFlow, domain=DOMAIN)，
                # 不吞掉这个 kwarg 会 TypeError
                "__init_subclass__": classmethod(lambda cls, **kwargs: None),
                "VERSION": 1,
                "async_set_unique_id": lambda self, *a, **kw: None,
                "_abort_if_unique_id_configured": lambda self, *a, **kw: None,
            },
        ),
        OptionsFlow=type("OptionsFlow", (_StubFlow,), {"config_entry": None}),
    )

    # exceptions
    mod(
        "homeassistant.exceptions",
        HomeAssistantError=type("HomeAssistantError", (Exception,), {}),
        ServiceValidationError=type("ServiceValidationError", (Exception,), {}),
        ConfigEntryNotReady=type("ConfigEntryNotReady", (Exception,), {}),
    )

    # helpers
    mod(
        "homeassistant.helpers.config_validation",
        string=str,
        boolean=bool,
        positive_int=int,
        config_entry_only_config_schema=lambda domain: {},
    )
    mod("homeassistant.helpers.typing", ConfigType=dict)
    mod("homeassistant.helpers.device_registry", DeviceInfo=dict)
    mod("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
    mod("homeassistant.helpers.entity_registry")
    mod("homeassistant.helpers.update_coordinator")

    entity_attrs = {
        "Entity": StubEntity,
        "cached_property": property,
        "callback": lambda func: func,
    }
    entity_attrs.update(extra_entity_attrs or {})
    mod("homeassistant.helpers.entity", **entity_attrs)
    mod(
        "homeassistant.helpers.restore_state",
        RestoreEntity=type("RestoreEntity", (StubEntity,), {}),
    )

    # selector
    sel = types.ModuleType("homeassistant.helpers.selector")
    sel.SelectSelector = lambda config: config
    sel.SelectSelectorConfig = lambda **kwargs: kwargs
    sel.SelectOptionDict = lambda **kwargs: kwargs
    sel.EntitySelector = lambda config: config
    sel.EntitySelectorConfig = lambda **kwargs: kwargs
    sel.NumberSelector = lambda config: config
    sel.NumberSelectorConfig = lambda **kwargs: kwargs
    sel.TextSelector = lambda config: config
    sel.TextSelectorConfig = lambda **kwargs: kwargs
    sel.SelectSelectorMode = type("SelectSelectorMode", (), {"DROPDOWN": "dropdown", "LIST": "list"})
    sys.modules["homeassistant.helpers.selector"] = sel

    # components
    class _StubLight(StubEntity):
        _attr_is_on = None
        _attr_effect = None
        _attr_effect_list = None
        _attr_brightness = None
        _attr_color_mode = None
        _attr_supported_color_modes = None
        _attr_supported_features = 0

        async def async_turn_on(self, **kwargs):
            raise NotImplementedError

        async def async_turn_off(self, **kwargs):
            raise NotImplementedError

    class _StubSwitch(StubEntity):
        _attr_is_on = None
        _attr_device_class = None

        async def async_turn_on(self, **kwargs):
            raise NotImplementedError

        async def async_turn_off(self, **kwargs):
            raise NotImplementedError

    mod(
        "homeassistant.components.light",
        ATTR_EFFECT="effect",
        ATTR_BRIGHTNESS="brightness",
        ColorMode=type("ColorMode", (), {"ONOFF": "onoff", "BRIGHTNESS": "brightness"}),
        LightEntityFeature=type(
            "LightEntityFeature", (), {"EFFECT": 4, "FLASH": 8, "TRANSITION": 2}
        ),
        LightEntity=_StubLight,
    )
    mod(
        "homeassistant.components.switch",
        SwitchEntity=_StubSwitch,
        SwitchDeviceClass=type("SwitchDeviceClass", (), {"SWITCH": "switch", "OUTLET": "outlet"}),
    )


__all__ = [
    "install",
    "mod",
    "check",
    "StubState",
    "StubEntity",
    "StubRuntime",
    "FakeRuntime",
    "StubEntry",
    "StubHass",
]
