# 极米神灯 (XGIMI Magic Lamp) for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![version](https://img.shields.io/badge/version-2.1.0-blue.svg)
![license](https://img.shields.io/badge/license-MIT-green.svg)

通过局域网 **UDP 直连**控制极米神灯的**灯**（日光灯 / 节律光）与**投影仪**开关。

* 🔌 **纯本地通信** —— 不经过极米云端，不依赖官方 App
* 📦 **零依赖** —— `requirements: []`，只用 HA 自带的 asyncio UDP，不用装任何东西
* 🛠️ **指令文本可配置** —— 不同机型/固件指令串不一样时，在 UI 里改就行，不用碰代码
* 🎯 **两种实体形态** —— 3 实体（灯 ×2 + 投影）或 2 实体（灯 + 投影）任选

> 协议由抓包逆向得出，非官方实现。已在 XGIMI 神灯（`mode=5`）上实测验证。

## 安装

### 方式一：HACS（推荐）

1. HACS → 右上角 `⋮` → **自定义存储库**
2. 填入 `https://github.com/Lzk119/XGMI_HA`，类别选 **集成（Integration）**
3. 搜索 **极米神灯** → 下载
4. **重启 Home Assistant**
5. 「设置 → 设备与服务 → 添加集成」搜索 **极米神灯**，填入设备 IP

### 方式二：手动

```bash
# 在 HA 配置目录（config/）下
git clone https://github.com/Lzk119/XGMI_HA.git /tmp/xgmi_ha
cp -r /tmp/xgmi_ha/custom_components/xgimi_lamp config/custom_components/
```

然后重启 HA，同上添加集成。

**要求**：Home Assistant `2024.4.0` 或更高；HA 主机与神灯在**同一局域网**。

## 生成的实体

集成提供两种**实体形态**，在「配置 → 选项 → 灯实体形态」里切换（默认"分开"）：

### 形态 A：分开（默认，3 个实体）

| 实体 | 类型 | 说明 |
| --- | --- | --- |
| `light.<设备名>_日光灯` | 灯 | 打开 = 发 `打开日光灯` |
| `light.<设备名>_节律光` | 灯 | 打开 = 发 `打开节律光灯光` |
| `switch.<设备名>_投影仪` | 开关 | 投影仪开 / 关 |

一台神灯只有一个灯，所以这两个灯实体是**互斥**的：点亮其中一个，另一个自动显示为关闭；
关掉任意一个，两个都归零（不会发出多余指令，只是状态同步）。

### 形态 B：单灯体（2 个实体）

| 实体 | 类型 | 说明 |
| --- | --- | --- |
| `light.<设备名>` | 灯 | 开关 + `effect` 下拉：**日光灯** / **节律光** |
| `switch.<设备名>_投影仪` | 开关 | 投影仪开 / 关 |

> ⚠️ HA 前端**只在灯为"开"的状态下才显示 `effect` 下拉框**（在"更多信息"面板里）。
> 想直接点一下就切模式，请用形态 A。
>
> 形态 B 里，如果不指定 `effect` 直接开灯，使用选项里的"默认开灯模式"。

集成状态是**乐观更新**（`iot_class: assumed_state`）——协议没有状态查询接口，
实体状态反映的是"最后一次下发的指令"，并通过 `RestoreEntity` 在 HA 重启后恢复。
投影仪开机需要数十秒，开关键变 on 不代表画面已亮。

## 配置项

「配置 → 选项」里可调整以下内容，保存后自动重载：

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| 灯实体形态 | `分开` | `分开` / `单灯体` |
| 默认开灯模式 | `日光灯` | 仅"单灯体"形态生效 |

指令文本（5 条，实测值）：

| 选项 | 默认值 | 来源 |
| --- | --- | --- |
| 开灯（日光灯） | `打开日光灯` | 实测验证 ✅ |
| 开灯（节律光） | `打开节律光灯光` | 抓包实证 + 实测验证 ✅ |
| 关灯 | `关灯` | 抓包实证 + 实测验证 ✅ |
| 打开投影仪 | `打开投影仪` | 待实测确认 ⚠️ |
| 关闭投影仪 | `关闭投影仪` | 待实测确认 ⚠️ |

> App 界面上把该模式叫「节律灯」，但线上实际传的是 `打开节律光灯光`。
> 默认取实测值；若你的设备不认，改成 `打开节律灯` 试试。

## 服务：`xgimi_lamp.send_command`

调试利器：不改代码直接把任意文本丢给设备，用来试出你的机型认哪个字符串。

```yaml
service: xgimi_lamp.send_command
data:
  command: 打开日光灯
  wait_response: true   # 可选，等待设备回包用于诊断
```

在「开发者工具 → 操作」里执行并勾选"返回响应"，可以看到：

```json
{"host": "192.168.1.100", "command": "打开日光灯", "local_port": 16751, "response": null}
```

## 协议（抓包实证）

控制链路只有 2 条 UDP 报文，格式完全一致：

**控制器 → 设备，目标端口 UDP 16750**

```json
{"action": 20000, "controlCmd": {"data": "打开节律光灯光", "delayTime": 0, "mode": 5, "time": 0, "type": 0}, "msgid": "2"}
{"action": 20000, "controlCmd": {"data": "关灯",           "delayTime": 0, "mode": 5, "time": 0, "type": 0}, "msgid": "2"}
```

**设备 → 控制器，目标端口 UDP 16751**（设备固定发到这个端口，而不是请求的源端口）

```json
{"action": 20001, "endScreenCapTime": 0, "msgid": "2", "startScreenCapTime": 0, "type": 0,
 "agreement": {"agreementType": 0, "isTcp": true, "msgId": "2", "phoneIp": "192.168.1.2", "port": 13145}}
```

| 项 | 值 | 说明 |
| --- | --- | --- |
| 传输层 | UDP | 无握手、无认证、无鉴权 |
| 控制端口 | 16750 | 设备监听 |
| 回包端口 | 16751 | 设备固定把回包发到这里，而非请求的源端口 |
| 编码 | UTF-8 JSON | 中文命令原文，`ensure_ascii=False` |
| `mode` | 5 | 神灯机型为 5 |
| `msgid` | `"2"` | **字符串**，不是整数 |
| `action` | 20000 控制 / 20001 应答 | |
| 指令载体 | `controlCmd.data` | 中文文本，神灯特有 |

### 与普通极米投影仪的差异

社区（[Xgimi-4-Home-Assistant](https://github.com/manymuch/Xgimi-4-Home-Assistant)）
在普通投影仪上抓到的是**两条**通道：

* 复杂指令：UDP `16750`，报文为 `{"action":20000,"controlCmd":{"delayTime":0,"mode":6,"time":0,"type":0},"msgid":"2"}` —— **没有 `data` 字段**，`mode` 为 6
* 简单按键：UDP `16735`，纯文本 `KEYPRESSES:116`（116 = 电源键）

**神灯走的是前者带 `data` 的变体**，本集成按抓包实证的这条实现，不要照抄社区报文格式。

## 排障

**完全没反应**

1. 确认设备 IP：路由器后台查，或看 UPnP 描述 `http://<设备IP>:1537/`
   （应返回 `friendlyName` 含「极米神灯」、`manufacturer` 为 `jimi`）
2. 确认 HA 主机和设备在**同一网段**（跨 VLAN / 子网会失败）
3. HA 跑在 Docker 里且未用 `--network=host` 时容易失败
4. 在「开发者工具 → 操作」里跑 `xgimi_lamp.send_command`，`wait_response` 设为 true 看有没有回包

**收不到设备回包（`response` 为 null）**

**这是正常现象，不代表指令失败。** 实测确认：

* 设备只会把应答发给**已注册的**控制器，HA 主机发的包通常收不到应答
* 该设备**不产生 ICMP 端口不可达**，所以也无法用 UDP connect 探活
* 设备把应答固定发到 **UDP 16751**，若官方「无屏助手」App 正在运行会占用该端口，
  本集成会自动退回随机端口（此时能控制，但收不到应答，日志里有提示）

**结论：判断指令是否生效，只能看灯/投影的实际反应。**

**打开日志**

```yaml
logger:
  default: warning
  logs:
    custom_components.xgimi_lamp: debug
```

**切换形态后旧实体残留？**

选项保存后集成会自动重载。若旧的 `light.<设备名>` 仍以 `unavailable` 出现在界面上，
重启一次 HA 即可，也可以在「设置 → 设备与服务 → 实体」里手动删掉。

## 开发

### 离线测试（不需要安装 Home Assistant）

`tests/` 里带了一套用桩模块模拟 `homeassistant.*` 的测试，直接 import 组件跑实体逻辑：

```bash
python tests/test_xgimi_lamp.py
```

覆盖 40 项断言：`effect` 特性位、两种形态各生成几个实体、实际发出的指令文本、
分开形态的互斥同步、乐观状态、`RestoreEntity` 恢复、选项表单字段/默认值/回显/校验。

### 排障工具

仓库 `tools/` 下有两个不依赖第三方库的脚本：

```bash
# 解析抓包，只看控制链路（自动过滤 SSDP/mDNS 噪音）
python tools/parse_pcap.py capture.pcap --port 16750 --port 16751

# 绕开 HA 直接给设备发指令，并尝试接收应答
python tools/send_command.py 192.168.1.100 "打开日光灯" --listen
```

`parse_pcap.py` 内置了一个极简 pcap 解析器（纯标准库，不装 scapy/tshark 也能用），
支持 VLAN 标签、UDP/TCP 载荷提取、JSON 格式化。

### 目录结构

```
.
├── custom_components/xgimi_lamp/   HA 集成本体
│   ├── __init__.py       集成入口，服务注册，config entry 生命周期
│   ├── const.py          协议常量与默认指令串
│   ├── protocol.py       UDP 客户端（收发、回包匹配、端口回退）
│   ├── runtime.py        config entry -> 运行时对象
│   ├── entity.py         实体基类（设备信息 / 发送封装）
│   ├── light.py          灯实体（两种形态 + 互斥同步）
│   ├── switch.py         投影仪开关实体
│   ├── config_flow.py    配置流程 + 选项流程
│   ├── services.yaml     服务定义
│   ├── manifest.json
│   ├── strings.json
│   └── translations/{en,zh-Hans}.json
├── tests/                          离线测试
│   ├── ha_stub.py        homeassistant 最小桩
│   └── test_xgimi_lamp.py
├── tools/                          排障脚本
│   ├── parse_pcap.py     极简 pcap 载荷提取器
│   └── send_command.py   直接向设备发指令
└── hacs.json
```

## 已知限制

* 协议**没有状态查询接口**，实体状态是乐观更新，可能与实际不符
  （例如别人用遥控器关了灯，HA 里仍显示开着）
* `打开投影仪` / `关闭投影仪` 两条指令尚未实机验证，如无效请在选项里改
* 仅支持局域网，不支持远程访问

## License

[MIT](LICENSE)
