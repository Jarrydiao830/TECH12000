# 待确认事项与未实现部分

以下内容**有意留空**，在拿到官方资料或实物测量结果之前不填写、不猜测。

## 等待资料才能实现

| 模块 | 文件 | 需要的资料 |
|---|---|---|
| APNs 发送 | `pc/tech12000/apns.py` | 第二阶段再做；需 Apple 开发者团队配置 |

各文件开头的注释列出了读文档时要确认的具体问题。

## Hiwonder 舵机控制器（驱动已实现，待实物确认）

依据 `docs/vendor/hiwonder/` 中的官方协议实现：USB 虚拟串口（CH341 系列）9600 波特，`CMD_SERVO_MOVE` 无应答，
每秒用 `CMD_GET_BATTERY_VOLTAGE` 查询电压作为在线检测。仍需实物确认：

- macOS 是否直接枚举出 `/dev/cu.*`（厂家只提供 Windows 版 CH341 驱动）。
- 通道 0 是否可用：丝印为 0–15，但厂家示例把 ID 限制在 1–254。建议释放舵机接 1–3 号（同时带过流保护）。
- 上电瞬间各通道的输出行为（手册只写"上电后不会直接回到中位"）。
- 控制器电源通路电流能力（手册未给出）与 X70S 堵转电流是否匹配；跳线帽对应的低压报警阈值（5 V / 6.4 V）。
- 仅接 USB、不接电池时，控制器是否会应答电压查询（不应答则驱动判为未就绪，无法使能）。

## 亚博 IMU（驱动已实现，待实物确认）

依据 `docs/vendor/yahboom-imu/` 中的通信协议表与模块介绍：串口 115200、帧 `7E 23 LEN FUNC … SUM`，
0x04 帧为 int16 原始加速度/角速度（比例 16/32767 g、2000/32767 °/s），默认 25 Hz、可设 10~100 Hz，
上电约 5 s 后就绪，帧内无时间戳。手环固件开机后 10 s 内每秒下发一次"设为 100 Hz"（该命令无应答）。

接线（`board_config.h`）：IMU TX → XIAO D7，IMU RX → XIAO D6，GND 共地。

仍需确认：

- **串口电平**：文档只写"工作电压 5V 或 3.3V"，没写 TX 输出电平。XIAO ESP32-S3 的 IO 不耐 5 V。
  建议用 XIAO 的 3V3 给模块 3V3 脚供电，并在接 XIAO 之前用万用表量一下模块 TX 空闲电压不超过 3.3 V。
- 实物是 6 / 9 / 10 轴哪一版（协议相同；本项目只用加速度和角速度）。
- 100 Hz 设置是否生效：手环串口每 5 s 打印 IMU 帧数，或先用 `tech12000 imu-probe --port … --rate 100` 直连确认。
- 传感器坐标轴方向（板上丝印 X/Y/Z）；当前融合规则只用合加速度和合角速度，不依赖方向。
- 手环固件已于 2026-11-16 在 Windows 上用 PlatformIO 编译通过（espressif32 8.0.0），尚未上板；协议解析部分已用 `firmware/test/test_yb_imu_protocol.cpp` 在电脑上测试。

## RS6240 雷达（驱动已实现，待实物确认）

资料与依据见 `docs/vendor/rs6240/`。要点：

- 底板 USB 是一颗 CH347T。**出厂 Sample 固件的点云（HIF）走 SPI**，Mac 读不到；
  所以演示用厂家 HostSample 附带的 `Tracking_uart_mrs6240_p2512.img`（HIF 走 UART）。
- 电脑端只监听、不发命令；解析 HIF 帧（0xA5 + Check8 + 消息头 + Check32）和 0xC3 点云分片重组。
- 现成固件**只输出点云，没有跟踪目标、没有跌倒算法**。"目标高度"由电脑端从点云估计
  （`fusion.radar.points`，基线规则，未标定）。Tracking 固件只出移动点云，人静止时没有点。

### 在 Windows 上做（一次性）

1. 装驱动：`radar/USB Serial Driver.zip` 里的 CH347 驱动；工具用 SDK 里的 RadarDebugTool。
2. 拨码按"UART-SPI"模式（FUNC SEL 1、2、5、6、7、9 ON，其余 OFF；MODE SEL ON）。
3. 进烧录模式：POWER 拨 OFF → 按住 UPD → POWER 拨 ON → 保持约 2 秒松开。
4. RadarDebugTool 选 SPI、60 MHz，Connect → Download 选 `docs/vendor/rs6240/Tracking_uart_mrs6240_p2512.img`，
   到 100% 后按 NRST 复位。（步骤出自《RS6x_7x_毫米波雷达开发_快速入门》4.3）

### 回到 Mac 上验证

```
.venv/bin/tech12000 ports
.venv/bin/tech12000 radar-probe --port /dev/cu.XXXX --seconds 10 --save data/radar_probe.bin
```

- 有 `frame ... points=` 输出即链路打通；再写 `config/local.yaml`：`sources.radar.driver: rs6240`、`port`、`baud`。
- 0 帧时依次排查：波特率改 115200 / 2000000；拨码是否把 UART0 接到 Type-C；
  这份固件是否需要主机先唤醒/轮询（HIF 手册 6.3，需补主机命令，目前未实现）。
- 确定竖直轴：人站立、蹲下、躺下时看 `radar-probe` 打印的 z 范围，再填 `fusion.radar.points.height_axis / height_sign / height_offset_m`。

### 仍未确认

- 这份 UART 固件的实际波特率（1 Mbps 取自厂家 ESP32 主机示例预设）以及是否主动上报。
- 真机 Check32 是否全部通过（厂家 SPI 示例文档提到某固件 Check32 有偏差）；失败帧当前直接丢弃。
- 坐标系方向、安装姿态；极坐标点云的轴向约定（目前不换算，只计数）。
- motion 与 presence 点云若共用同一 frameIdx 交替分片，当前重组会丢帧（Posture 固件才有 presence）。
- 若要 5 m 内近距离、含存在点云的 Posture 固件走 UART，需在 Windows 上用 CDK 重新编译。

## 需要按实物填写的配置

- `firmware/wristband/src/board_config.h`：接收板 MAC（IMU 引脚/波特率已按下节填写）。
- `firmware/receiver/src/board_config.h`：LED 引脚、按钮引脚。
- `config/local.yaml`：串口设备名；舵机通道、初始位置、释放位置、演示位置、动作时间。

## 尚未标定 / 验证

- `config/default.yaml` 中 `fusion` 下所有阈值都是占位值，只为模拟模式能跑通。
- 状态机是"两路候选时间吻合"的基线规则，未经任何真实数据验证。
- 内置模拟波形是人为构造的，不能用来评估误报、漏报或提前量。
- 端到端延迟（IMU 采样 → 舵机动作 → 充气完成）尚未测量。
- 时间对齐只估计了时钟偏差，最小链路延迟需要另做实验标定。

## macOS 相关风险

- RS6240 底板是 CH347T；烧录与 IDE 只有 Windows 版。Mac 只负责读 UART 固件的数据，能否免驱识别 CH347T 待实物确认。
- Hiwonder 控制器经 CH341 系列 USB 转串口连接（官方使用说明），macOS 能否免驱枚举待实物确认。

## 未编译验证

- iOS App 源码在 Linux 环境下写成，未经 Xcode 编译，首次打开可能需要小幅修正。

## 仍需硬件层面考虑

- 建议在舵机电源上加独立的物理开关作为联锁，软件 ARMED 不应是唯一屏障。
- 舵机独立供电、共地、保险保护；控制器供电通路电流能力需对照 X70S 峰值电流。
