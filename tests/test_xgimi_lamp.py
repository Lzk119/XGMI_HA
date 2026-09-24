"""xgimi_lamp 集成测试：不需要安装 Home Assistant。

    python tests/test_xgimi_lamp.py

用 tests/ha_stub.py 桩出 `homeassistant.*`，然后直接 import 组件、
调用实体方法，验证真正容易踩坑的那部分逻辑：

* effect 特性位是否声明（少了它前端不渲染下拉框）
* 两种实体形态各生成几个实体、发什么指令
* 分开形态下两个灯实体的互斥状态同步
* RestoreEntity 状态恢复
* 选项表单字段、默认值、回显与校验
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ha_stub import (  # noqa: E402
    StubEntry,
    StubHass,
    StubRuntime,
    StubState,
    check,
    install,
)

install()

from custom_components.xgimi_lamp import config_flow as cf  # noqa: E402
from custom_components.xgimi_lamp import light as light_mod  # noqa: E402
from custom_components.xgimi_lamp.const import (  # noqa: E402
    CONF_DEFAULT_LIGHT_MODE,
    CONF_LIGHT_SHAPE,
    DEFAULT_COMMANDS,
    DOMAIN,
    LIGHT_MODE_DAYLIGHT,
    LIGHT_MODE_RHYTHM,
    LIGHT_SHAPE_SINGLE,
    LIGHT_SHAPE_SPLIT,
)

DAYLIGHT_ON = DEFAULT_COMMANDS["cmd_light_daylight"]  # 打开日光灯
RHYTHM_ON = DEFAULT_COMMANDS["cmd_light_rhythm"]  # 打开节律光灯光
LIGHT_OFF = DEFAULT_COMMANDS["cmd_light_off"]  # 关灯


async def setup_lights(options: dict):
    """跑一遍灯平台的 async_setup_entry，返回 (运行时, 实体列表)。"""
    runtime = StubRuntime(DEFAULT_COMMANDS)
    added: list = []
    await light_mod.async_setup_entry(
        StubHass(DOMAIN, runtime), StubEntry(options), lambda entities: added.extend(entities)
    )
    for entity in added:
        entity.hass = object()  # 模拟"已加入 HA"
        await entity.async_added_to_hass()
    return runtime, added


# ---------------------------------------------------------------------------
# 单灯体形态
# ---------------------------------------------------------------------------
async def test_single_shape() -> None:
    print("\n--- 形态 B：单灯体（灯 + effect 下拉）---")
    runtime, added = await setup_lights({CONF_LIGHT_SHAPE: LIGHT_SHAPE_SINGLE})
    check("生成 1 个灯实体", len(added) == 1, str(len(added)))
    ent = added[0]

    check(
        "声明了 EFFECT 特性位（否则前端不显示下拉框）",
        ent._attr_supported_features == light_mod.LightEntityFeature.EFFECT,
        f"supported_features={ent._attr_supported_features}",
    )
    check(
        "effect_list 含两种模式",
        list(ent._attr_effect_list) == [LIGHT_MODE_DAYLIGHT, LIGHT_MODE_RHYTHM],
        str(ent._attr_effect_list),
    )
    check("初始为关闭", ent._attr_is_on is False)

    await ent.async_turn_on()
    check("不带 effect 开灯用默认模式", runtime.client.sent[-1] == DAYLIGHT_ON, runtime.client.sent[-1])
    check("乐观状态置为 on", ent._attr_is_on is True)

    await ent.async_turn_on(effect=LIGHT_MODE_RHYTHM)
    check("带 effect 开灯发节律光", runtime.client.sent[-1] == RHYTHM_ON, runtime.client.sent[-1])
    check("effect 被记录", ent._attr_effect == LIGHT_MODE_RHYTHM, ent._attr_effect)

    await ent.async_turn_on()
    check("再次开灯沿用上次模式", runtime.client.sent[-1] == RHYTHM_ON, runtime.client.sent[-1])

    await ent.async_turn_off()
    check("关灯发『关灯』", runtime.client.sent[-1] == LIGHT_OFF, runtime.client.sent[-1])
    check("关灯后 is_on=False", ent._attr_is_on is False)

    # 自定义默认模式
    runtime2, added2 = await setup_lights(
        {CONF_LIGHT_SHAPE: LIGHT_SHAPE_SINGLE, CONF_DEFAULT_LIGHT_MODE: LIGHT_MODE_RHYTHM}
    )
    await added2[0].async_turn_on()
    check("默认模式选项生效", runtime2.client.sent[-1] == RHYTHM_ON, runtime2.client.sent[-1])

    # 非法默认模式回退
    runtime3, added3 = await setup_lights(
        {CONF_LIGHT_SHAPE: LIGHT_SHAPE_SINGLE, CONF_DEFAULT_LIGHT_MODE: "???"}
    )
    await added3[0].async_turn_on()
    check("非法默认模式回退到日光灯", runtime3.client.sent[-1] == DAYLIGHT_ON, runtime3.client.sent[-1])

    # 状态恢复
    ent4 = light_mod.XgimiLampLight(StubRuntime(DEFAULT_COMMANDS), LIGHT_MODE_DAYLIGHT)
    ent4.hass = object()
    ent4._stub_last_state = StubState("on", {"effect": LIGHT_MODE_RHYTHM})
    await ent4.async_added_to_hass()
    check(
        "重启后恢复开关与模式",
        ent4._attr_is_on is True and ent4._attr_effect == LIGHT_MODE_RHYTHM,
        f"is_on={ent4._attr_is_on}, effect={ent4._attr_effect}",
    )


# ---------------------------------------------------------------------------
# 分开形态
# ---------------------------------------------------------------------------
async def test_split_shape() -> None:
    print("\n--- 形态 A：分开（日光灯 / 节律光 各一个实体）---")
    runtime, added = await setup_lights({})
    check("默认形态生成 2 个灯实体", len(added) == 2, str(len(added)))
    daylight, rhythm = added

    check(
        "实体名与模式对应",
        daylight._attr_name == LIGHT_MODE_DAYLIGHT and rhythm._attr_name == LIGHT_MODE_RHYTHM,
        f"{daylight._attr_name} / {rhythm._attr_name}",
    )
    check(
        "unique_id 与模式绑定",
        daylight._attr_unique_id.endswith("light_daylight")
        and rhythm._attr_unique_id.endswith("light_rhythm"),
        f"{daylight._attr_unique_id} / {rhythm._attr_unique_id}",
    )

    await daylight.async_turn_on()
    check("日光灯实体发『打开日光灯』", runtime.client.sent[-1] == DAYLIGHT_ON, runtime.client.sent[-1])
    check(
        "点亮日光灯后节律灯自动熄灭",
        daylight._attr_is_on is True and rhythm._attr_is_on is False,
        f"日光={daylight._attr_is_on}, 节律={rhythm._attr_is_on}",
    )

    await rhythm.async_turn_on()
    check("节律灯实体发『打开节律光灯光』", runtime.client.sent[-1] == RHYTHM_ON, runtime.client.sent[-1])
    check(
        "点亮节律灯后日光灯自动熄灭",
        daylight._attr_is_on is False and rhythm._attr_is_on is True,
        f"日光={daylight._attr_is_on}, 节律={rhythm._attr_is_on}",
    )

    await rhythm.async_turn_off()
    check("关灯发『关灯』", runtime.client.sent[-1] == LIGHT_OFF, runtime.client.sent[-1])
    check(
        "关灯后两个实体都归零",
        daylight._attr_is_on is False and rhythm._attr_is_on is False,
        f"日光={daylight._attr_is_on}, 节律={rhythm._attr_is_on}",
    )
    check("互斥同步没有多发指令", len(runtime.client.sent) == 3, str(runtime.client.sent))


async def test_setup_branches() -> None:
    print("\n--- 实体数量分支 ---")
    cases = [
        ({}, 2, "未设置选项 -> 分开（默认）"),
        ({CONF_LIGHT_SHAPE: LIGHT_SHAPE_SPLIT}, 2, "split"),
        ({CONF_LIGHT_SHAPE: LIGHT_SHAPE_SINGLE}, 1, "single"),
        ({CONF_LIGHT_SHAPE: "???"}, 2, "非法取值回退到分开"),
    ]
    for options, expected, label in cases:
        _, added = await setup_lights(options)
        check(f"{label} -> {expected} 个灯实体", len(added) == expected, f"实际 {len(added)}")


# ---------------------------------------------------------------------------
# 选项流程
# ---------------------------------------------------------------------------
def schema_defaults(schema) -> dict:
    """从假 voluptuous Schema 里取出 {字段名: 默认值}。"""
    return {marker.key: marker.default for marker in schema}


async def test_options_flow() -> None:
    print("\n--- 选项流程 ---")
    flow = cf.XgimiLampOptionsFlow()
    flow.config_entry = StubEntry({})
    defaults = schema_defaults((await flow.async_step_init(None))["data_schema"])

    check("表单含『灯实体形态』", CONF_LIGHT_SHAPE in defaults)
    check(
        "形态默认取分开",
        defaults[CONF_LIGHT_SHAPE] == LIGHT_SHAPE_SPLIT,
        str(defaults[CONF_LIGHT_SHAPE]),
    )
    check("表单含『默认开灯模式』", CONF_DEFAULT_LIGHT_MODE in defaults)
    check(
        "默认模式默认为日光灯",
        defaults[CONF_DEFAULT_LIGHT_MODE] == LIGHT_MODE_DAYLIGHT,
        str(defaults[CONF_DEFAULT_LIGHT_MODE]),
    )
    check(
        "形态下拉有两个选项",
        {o["value"] for o in cf.SHAPE_SELECTOR["options"]}
        == {LIGHT_SHAPE_SPLIT, LIGHT_SHAPE_SINGLE},
        str([o["value"] for o in cf.SHAPE_SELECTOR["options"]]),
    )

    # 回显
    flow2 = cf.XgimiLampOptionsFlow()
    flow2.config_entry = StubEntry(
        {CONF_LIGHT_SHAPE: LIGHT_SHAPE_SINGLE, CONF_DEFAULT_LIGHT_MODE: LIGHT_MODE_RHYTHM}
    )
    defaults2 = schema_defaults((await flow2.async_step_init(None))["data_schema"])
    check(
        "已有选项正确回显",
        defaults2[CONF_LIGHT_SHAPE] == LIGHT_SHAPE_SINGLE
        and defaults2[CONF_DEFAULT_LIGHT_MODE] == LIGHT_MODE_RHYTHM,
        f"{defaults2[CONF_LIGHT_SHAPE]} / {defaults2[CONF_DEFAULT_LIGHT_MODE]}",
    )

    # 非法值回退
    flow3 = cf.XgimiLampOptionsFlow()
    flow3.config_entry = StubEntry({CONF_LIGHT_SHAPE: "x", CONF_DEFAULT_LIGHT_MODE: "y"})
    defaults3 = schema_defaults((await flow3.async_step_init(None))["data_schema"])
    check(
        "非法选项回退到默认值",
        defaults3[CONF_LIGHT_SHAPE] == LIGHT_SHAPE_SPLIT
        and defaults3[CONF_DEFAULT_LIGHT_MODE] == LIGHT_MODE_DAYLIGHT,
        f"{defaults3[CONF_LIGHT_SHAPE]} / {defaults3[CONF_DEFAULT_LIGHT_MODE]}",
    )

    # 校验：指令串不能为空
    bad = await flow.async_step_init(
        {
            CONF_LIGHT_SHAPE: LIGHT_SHAPE_SPLIT,
            CONF_DEFAULT_LIGHT_MODE: LIGHT_MODE_DAYLIGHT,
            "cmd_light_daylight": DAYLIGHT_ON,
            "cmd_light_rhythm": RHYTHM_ON,
            "cmd_light_off": "   ",
            "cmd_projector_on": "打开投影仪",
            "cmd_projector_off": "关闭投影仪",
        }
    )
    check("空指令串被拦下", bad.get("errors", {}).get("base") == "empty_command", str(bad.get("errors")))

    good = await flow.async_step_init(
        {
            CONF_LIGHT_SHAPE: LIGHT_SHAPE_SINGLE,
            CONF_DEFAULT_LIGHT_MODE: LIGHT_MODE_RHYTHM,
            "cmd_light_daylight": DAYLIGHT_ON,
            "cmd_light_rhythm": RHYTHM_ON,
            "cmd_light_off": f"  {LIGHT_OFF}  ",
            "cmd_projector_on": "打开投影仪",
            "cmd_projector_off": "关闭投影仪",
        }
    )
    check("正常保存", good.get("type") == "create_entry", str(good.get("type")))
    check("指令串去除首尾空格", good["data"]["cmd_light_off"] == LIGHT_OFF)
    check(
        "形态与默认模式一并保存",
        good["data"][CONF_LIGHT_SHAPE] == LIGHT_SHAPE_SINGLE
        and good["data"][CONF_DEFAULT_LIGHT_MODE] == LIGHT_MODE_RHYTHM,
    )


async def main() -> None:
    await test_single_shape()
    await test_split_shape()
    await test_setup_branches()
    await test_options_flow()
    print("\n全部通过 ✅")


if __name__ == "__main__":
    asyncio.run(main())
