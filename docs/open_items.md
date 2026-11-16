# 待确认事项与未实现部分

以下内容**有意留空**，在拿到官方资料或实物测量结果之前不填写、不猜测。

## 等待资料才能实现

| 模块 | 文件 | 需要的资料 |
|---|---|---|
| 亚博六轴 IMU 解析 | `firmware/wristband/src/imu_yahboom.cpp` | 模块准确型号、串口协议、供电与电平 |
| RS6240 雷达驱动 | `pc/tech12000/sources/radar_rs6240.py` | 开发板使用手册、SDK、数据帧格式、坐标定义 |
| Hiwonder 舵机控制器驱动 | `pc/tech12000/actuators/servo_hiwonder.py` | 手册、电脑通信协议、供电能力 |
| APNs 发送 | `pc/tech12000/apns.py` | 第二阶段再做；需 Apple 开发者团队配置 |

各文件开头的注释列出了读文档时要确认的具体问题。

## 需要按实物填写的配置

- `firmware/wristband/src/board_config.h`：IMU 的 RX/TX 引脚、波特率；接收板 MAC。
- `firmware/receiver/src/board_config.h`：LED 引脚、按钮引脚。
- `config/local.yaml`：串口设备名；舵机通道、初始位置、释放位置、演示位置、动作时间。

## 尚未标定 / 验证

- `config/default.yaml` 中 `fusion` 下所有阈值都是占位值，只为模拟模式能跑通。
- 状态机是"两路候选时间吻合"的基线规则，未经任何真实数据验证。
- 内置模拟波形是人为构造的，不能用来评估误报、漏报或提前量。
- 端到端延迟（IMU 采样 → 舵机动作 → 充气完成）尚未测量。
- 时间对齐只估计了时钟偏差，最小链路延迟需要另做实验标定。

## macOS 相关风险

- RS6240 官方 IDE 与 USB 驱动包是 Windows 版；macOS 能否直接读数据取决于底板上两个 USB 转串口芯片的型号。
- Hiwonder 控制器在 macOS 上的连接方式（HID 或虚拟串口）待确认。

## 未编译验证

- iOS App 源码在 Linux 环境下写成，未经 Xcode 编译，首次打开可能需要小幅修正。

## 仍需硬件层面考虑

- 建议在舵机电源上加独立的物理开关作为联锁，软件 ARMED 不应是唯一屏障。
- 舵机独立供电、共地、保险保护；控制器供电通路电流能力需对照 X70S 峰值电流。
