# TECH12000 交接说明（给新的本地会话）

本文概述到目前为止做了什么、怎么设计的、哪些没做。配合原始需求文档一起读。

## 1. 项目一句话

浴室跌倒检测研究原型：固定式毫米波雷达 + 无线手环 → 电脑融合判断 → 控制 LED 和舵机（驱动气囊释放机构）→ 状态推送到只读的 iOS App。电脑是唯一决策中心，无云服务器。

## 2. 硬件与环境（已确认的事实）

- 雷达：正和微芯 RS6240 开发套件 = MRS6240-P2512 模组（60 GHz，2发4收）+ MRS6240-AIP-DEV-V1 底板，USB-C 接电脑。
- 手环：亚博六轴 IMU →（UART）→ Seeed XIAO ESP32-S3 →（ESP-NOW）→ 固定端。
- 固定端：ESP32-S3-DevKitC-1 类开发板（N16R8）→ USB 串口 → 电脑；同时驱动 LED。
- 执行：电脑 → USB → 幻尔 Hiwonder 16路舵机控制器 → X70S 舵机（6–8.4 V，脉宽 500–2500 μs）。
- 电脑：macOS 27.0.1。
- 第一版单手环、单人；其余板子为备用。

## 3. 厂家资料现状

| 资料 | 来源 | 状态 |
|---|---|---|
| 亚博 IMU 教程 | https://www.yahboom.com/study/IMU_Sensor （提取码 ibhe） | 已拿到，关键文件在 `docs/vendor/yahboom-imu/` |
| Hiwonder 控制器 | https://pan.baidu.com/s/1JmjeTW04JW6pkZnwtzMNyg （提取码 nfc5） | 已拿到，关键文件在 `docs/vendor/hiwonder/` |
| RS6240 | https://www.possumic.com/rs6240-aip-dev-box.html | 已拿到 SDK V2.1.2，关键文件在 `docs/vendor/rs6240/` |

RS6240 页面列出的文件：模组规格书 V1.0、开发板使用手册 V1.3、`RS6x_7x_mmWave_sdk.7z` V2.1.2、`cdk-windows.zip`（IDE，仅 Windows）、`USB Serial Driver.zip`（"驱动有两个，均需安装"）。页面写的采数接口为 UART/SPI/I2C。

**macOS 风险**：雷达 IDE 和驱动包是 Windows 版；能否在 Mac 上直接读数据取决于底板两个 USB 转串口芯片的型号。换固件可能需要 Windows。Hiwonder 在 Mac 上是 HID 还是虚拟串口也未知。

## 4. 不可违反的约束

1. 不编造厂家帧格式、GPIO、阈值、性能数据。资料不足就留接口 + 模拟模式。
2. 默认禁止实际释放。模式 MONITOR / DEMO / ARMED；启动和复位后一律回到 MONITOR，不自动使能。
3. 同一 event_id 只执行一次；重启、USB 重连、重复消息、网络重试都不能造成二次释放。
4. 没有展开反馈：只显示"指令已发送"（协议支持时显示"控制器确认"），实际展开状态恒为"未知／待检查"。不出现"已展开""保护成功"。
5. 数据过期或断联必须进入 Fault，不用旧数据判断。
6. 不同设备时钟不直接比较；分别保存设备时间、接收板时间、电脑接收时间。
7. 仅手环剧烈运动不能触发；"两路同时超阈值"不算已验证算法。
8. iOS App 只读，不提供远程释放或使能。前台弹窗不称为锁屏推送。
9. Apple 账号密码、APNs 私钥不进聊天、不进仓库，只走本地配置或环境变量。
10. 舵机控制器是 Hiwonder，不能套用 Pololu Maestro 协议。XIAO 按普通版处理，不假设板载 IMU。IMU 只假设六轴。

## 5. 已完成的内容（仓库 github.com/Jarrydiao830/TECH12000，main 分支）

### 电脑端 Python（`pc/tech12000/`）— 可运行，52 项测试通过（Python 3.10+，Mac 上用 3.14）

| 文件 | 作用 |
|---|---|
| `config.py` + `config/default.yaml` | YAML 配置，pydantic 校验，`local.yaml` 覆盖，配置指纹写入日志 |
| `models.py` | ImuSample / RadarFrame / FallEvent、状态与模式枚举、通知文案 |
| `timebase.py` | 设备时钟偏差估计（滑动窗口最小值） |
| `health.py` | 每条链路的序号连续性、重复、丢包、新鲜度 |
| `fusion/features.py` | 手环：合加速度、变化率、合角速度；雷达：目标高度及窗口内下降量 |
| `fusion/state_machine.py` | Initializing / Ready / Suspected / Triggered（锁定）/ Fault |
| `store.py` | SQLite：事件、执行台账（event_id 主键，先落盘再发指令）、APNs token |
| `executor.py` | 按模式执行；脉宽越界拒绝；失败不重试 |
| `engine.py` | 核心：输入 → 对齐 → 状态机 → 事件 → 执行；只依赖传入时间戳，实时与回放同一逻辑 |
| `recorder.py` / `replay.py` | JSONL 会话日志（独立写盘线程）；离线回放 |
| `sources/sim.py` | 模拟手环与雷达，剧本：静止/跌倒/挥手/慢蹲 |
| `sources/wristband_serial.py` | 读固定端串口（自定义 JSON 行协议），自动重连 |
| `sources/radar_rs6240.py` + `rs6240_hif.py` | 按厂家源码实现 HIF/0xC3 点云解析（只监听），需先烧 UART 固件，未接实物 |
| `actuators/servo_hiwonder.py` | 按官方 LSC 协议实现（9600 串口、电压查询作在线检测、移动指令无应答），未接实物 |
| `actuators/base.py` | 舵机/LED 接口、模拟实现、经接收板的 LED |
| `server/operator.py` + `static/index.html` | 本机监控台，仅 127.0.0.1，含使能/复位/曲线/配对二维码 |
| `server/mobile.py` | 手机只读接口：HTTP + WebSocket，Bearer 令牌 |
| `apns.py` | **占位**，只登记 token |
| `main.py` | `tech12000 run / replay / ports / radar-probe / imu-probe` |
| `sources/yb_imu.py` | 亚博 IMU 协议的电脑端解析，只给 `imu-probe` 直连排查用 |

状态机基线规则：手环候选（窗口内出现冲击或失重，且角速度超阈值）与雷达候选（窗口内高度下降超阈值）在 `coincidence_s` 内吻合才触发；任一候选只到 Suspected，超时回 Ready。**所有阈值是占位值，规则未经真实数据验证。**

进入 ARMED 的条件：状态 Ready + 舵机驱动就绪 + 通道/释放位置/动作时间已配置 + 本机界面输入 `ARM` 确认。

### 固件（`firmware/`，PlatformIO + Arduino）— 三个环境均已编译通过，未上板

2026-11-16 在 Windows 上编译：PlatformIO Core 6.2.0，平台 espressif32 8.0.0（Arduino-ESP32 3.3.12）。
`receiver`、`wristband_sim`、`wristband` 都一次通过，无报错；只把接收板里一处 `volatile` 自增的弃用警告改掉了。
Flash 占用约 25%（按默认 4 MB 分区表算）。

- `common/protocol.h`：ESP-NOW 定长包（magic、version、flags、device_id、session_id、seq、t_mcu_us、t_imu_us、accel[3] m/s²、gyro[3] °/s、crc16）。
- `wristband/src/yb_imu_protocol.h`：亚博 IMU 协议解析（纯 C++），`firmware/test/test_yb_imu_protocol.cpp` 可在电脑上单独编译测试。
- `wristband/`：环境 `wristband_sim`（固件内模拟 100 Hz IMU，用于先打通链路）和 `wristband`（真实 IMU，按亚博协议实现，已编译未上板）。发送失败即丢，不排队。不上报电量。
- `receiver/`：收包 → 校验/去重 → 加接收时间 → 每包一行 JSON；1 Hz 状态上报；接收电脑的 LED 指令；可选按钮只上报；电脑超时则 LED 故障闪烁。
- IMU 接 D7/D6、115200；接收板引脚仍待填。ESP-NOW 信道暂定 1，手环暂发广播地址。

### iOS（`ios/`）— 只有源码，未经 Xcode 编译

SwiftUI：状态页、事件历史与详情、设置页（手填或 `tech12000://pair?...` 二维码配对）、前台全屏告警、按 event_id 去重、令牌存钥匙串、5 秒无更新显示离线。XcodeGen 的 `project.yml` 生成工程。

### 文档

`README.md`（运行方法）、`docs/protocol.md`（自定义协议）、`docs/open_items.md`（留空项清单）。

## 6. 没做的事

- 三个厂家驱动都已按资料实现，均未接实物验证；固件只编译过，未上板。
- 真实硬件上的任何验证：固件未上板，串口链路未实测。
- 阈值标定、误报/漏报/提前量评估、端到端延迟测量。
- APNs 发送（第二阶段）。
- iOS 编译与真机运行。
- 断联/重连/重复事件的真机测试；机械释放与充气测试。

## 7. 设计上值得保留的决定

- 操作员服务与手机服务分两个端口：前者只听回环地址并校验 Host/Origin，后者监听局域网且没有任何写控制的路由。
- 引擎不读时钟，只用数据自带时间戳，因此回放结果与实时一致。
- 接收板与电脑之间用 JSON 行协议，便于直接用串口监视器调试。
- 固件提供模拟 IMU 构建，在拿到 IMU 协议前就能验证无线链路。

## 8. 下一步（2026-11-16 更新）

**使用者不熟悉编程和硬件，请一步一步带着做：每次只给一步，说明在哪里点、输入什么、看到什么算成功，等对方回复结果再继续。**

厂家资料原始包（`servo/`、`imu/`、`radar/`）在 Mac 上，被 `.gitignore` 排除，不在仓库里。
三个驱动的依据、未确认事项和实物验证步骤都在 `docs/open_items.md`。

### 在 Windows 上
1. ~~装 VS Code + PlatformIO IDE 插件。~~ 已完成（2026-11-16）。
2. ~~分别编译 `firmware/receiver`、`firmware/wristband` 的两个环境。~~ 已完成，三个都通过。
3. 烧 `receiver` 和 `wristband_sim`，串口监视器看输出（接收板 921600，见 `receiver/src/board_config.h` 的 `SERIAL_BAUD`；手环 115200）；记下接收板打印的 MAC。
4. 给 RS6240 烧 `Tracking_uart_mrs6240_p2512.img`（步骤见 `docs/open_items.md` RS6240 一节）。

### 回到 Mac 上
5. IMU 模块 USB 直连：`tech12000 imu-probe --port ... --rate 100`，静止时 |a| ≈ 9.8、约 100 Hz。
6. 量 IMU TX 电平 ≤ 3.3 V 后按 D7/D6 接 XIAO，烧 `wristband`，电脑端 `sources.wristband.driver: serial`，打通链路，测丢包与延迟。
7. 雷达：`tech12000 radar-probe --port ...`，确认能收到点云；站/蹲/躺定竖直轴，填 `fusion.radar.points`。
8. Hiwonder：插 Mac 看串口、电压应答；释放机构小角度空载测试。
9. 录真实动作数据，用回放标定阈值。

提醒：从第一天起逐段测端到端延迟；建议在舵机电源上加物理开关作为联锁，软件使能不应是唯一屏障。
