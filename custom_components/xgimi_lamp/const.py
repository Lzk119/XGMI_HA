"""极米神灯（XGIMI）HA 集成常量定义。

控制协议经抓包确认（xgimi-lan.pcap，2026-09-24）：

    控制器 -> 设备   UDP 16750
    {"action": 20000, "controlCmd": {"data": "<中文指令>", "delayTime": 0,
     "mode": 5, "time": 0, "type": 0}, "msgid": "2"}

    设备 -> 控制器   UDP 16751（设备回包的目的端口）
    {"action": 20001, "msgid": "2", "agreement": {"...": "..."}}

注意：``mode`` 在神灯上为 5；社区在普通极米投影仪上抓到的是 6（且不带
``data`` 字段）。本集成按神灯的 ``data`` 文本协议实现。
"""

DOMAIN = "xgimi_lamp"

# --------------------------------------------------------------------------
# 配置项 / 选项
# --------------------------------------------------------------------------
CONF_HOST = "host"
CONF_NAME = "name"

# 可自定义的指令串（在"配置 -> 选项"里可改）
CONF_CMD_LIGHT_DAYLIGHT = "cmd_light_daylight"
CONF_CMD_LIGHT_RHYTHM = "cmd_light_rhythm"
CONF_CMD_LIGHT_OFF = "cmd_light_off"
CONF_CMD_PROJECTOR_ON = "cmd_projector_on"
CONF_CMD_PROJECTOR_OFF = "cmd_projector_off"

DEFAULT_NAME = "极米神灯"

# --------------------------------------------------------------------------
# 网络参数
# --------------------------------------------------------------------------
CONTROL_PORT = 16750  # 控制指令目标端口（设备监听）
RESPONSE_PORT = 16751  # 设备回包的目的端口（控制器监听）
KEYPRESS_PORT = 16735  # 极米"简单按键 API"端口，本集成未使用

# --------------------------------------------------------------------------
# 协议字段
# --------------------------------------------------------------------------
ACTION_CONTROL = 20000
ACTION_RESPONSE = 20001
DEFAULT_MODE = 5
DEFAULT_MSGID = "2"

# 等待设备回包的默认超时（秒）
COMMAND_TIMEOUT = 3.0

# --------------------------------------------------------------------------
# 灯光模式（对应 light 实体的 effect）
# --------------------------------------------------------------------------
LIGHT_MODE_DAYLIGHT = "日光灯"
LIGHT_MODE_RHYTHM = "节律光"

# --------------------------------------------------------------------------
# 默认指令串
#
# 抓包中实际出现过的是"打开节律光灯光"；App 界面上显示为"节律灯"。
# 此处默认取抓包实证值，若你的设备不认，可在选项里改成"打开节律灯"。
# --------------------------------------------------------------------------
DEFAULT_COMMANDS: dict[str, str] = {
    CONF_CMD_LIGHT_DAYLIGHT: "打开日光灯",
    CONF_CMD_LIGHT_RHYTHM: "打开节律光灯光",
    CONF_CMD_LIGHT_OFF: "关灯",
    CONF_CMD_PROJECTOR_ON: "打开投影仪",
    CONF_CMD_PROJECTOR_OFF: "关闭投影仪",
}

# 灯光模式 -> 指令串配置项的映射
LIGHT_MODE_TO_CONF: dict[str, str] = {
    LIGHT_MODE_DAYLIGHT: CONF_CMD_LIGHT_DAYLIGHT,
    LIGHT_MODE_RHYTHM: CONF_CMD_LIGHT_RHYTHM,
}

LIGHT_MODES: list[str] = list(LIGHT_MODE_TO_CONF)

# --------------------------------------------------------------------------
# 灯实体形态（在"配置 -> 选项"里切换）
# --------------------------------------------------------------------------
CONF_LIGHT_SHAPE = "light_shape"

# 分开：日光灯 / 节律灯 各一个开关实体 + 投影开关（共 3 个实体）
LIGHT_SHAPE_SPLIT = "split"
# 单灯体：一个灯实体用 effect 下拉切换模式 + 投影开关（共 2 个实体）
LIGHT_SHAPE_SINGLE = "single"

DEFAULT_LIGHT_SHAPE = LIGHT_SHAPE_SPLIT

# 单灯体形态下，直接点"开灯"（未指定 effect）时使用哪种模式
CONF_DEFAULT_LIGHT_MODE = "default_light_mode"
DEFAULT_LIGHT_MODE = LIGHT_MODE_DAYLIGHT

# 灯模式 -> 实体 unique_id 后缀（分开形态使用）
LIGHT_MODE_TO_UNIQUE: dict[str, str] = {
    LIGHT_MODE_DAYLIGHT: "light_daylight",
    LIGHT_MODE_RHYTHM: "light_rhythm",
}

# 服务
SERVICE_SEND_COMMAND = "send_command"
ATTR_COMMAND = "command"
