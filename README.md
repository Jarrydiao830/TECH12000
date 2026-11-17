# TECH12000 浴室跌倒检测与气囊触发原型

固定式毫米波雷达 + 无线手环，电脑融合判断疑似跌倒，控制 LED 与舵机，并把状态推送到 iOS App。
不使用摄像头，不监测心率或呼吸。

**这是研究原型。** 跌倒检测、撞击前预测、气囊部署、缓冲效果是四个不同的验证目标；
"检测到并发出指令"不等于"气囊已展开"，更不等于"保护成功"。

## 当前进度

| 部分 | 状态 |
|---|---|
| 电脑端框架（采集/对齐/状态机/执行/日志/回放/界面/手机接口） | 可运行，模拟数据，52 项自动测试通过 |
| 接收板固件 | 2026-11-16 在 Windows 上用 PlatformIO 编译通过（espressif32 8.0.0），**未上板验证** |
| 手环固件（内置模拟 IMU） | 同上，编译通过，**未上板验证** |
| 手环固件（真实 IMU） | 已按亚博协议实现，解析器在电脑上单独测试通过；同上编译通过，**未上板验证** |
| RS6240 雷达驱动 | HIF 点云解析已按厂家源码实现，需先在 Windows 上烧 UART 固件，**未接实物验证** |
| Hiwonder 舵机控制器驱动 | 已按官方协议实现，帧与文档示例逐字节一致，**未接实物验证** |
| iOS App | Xcode 编译通过，模拟器中与模拟数据端到端跑通（配对、实时状态、前台告警、本地通知）；**未上真机** |
| APNs 锁屏推送 | 未实现（第二阶段） |

检测阈值全部是未标定的占位值。详见 [docs/open_items.md](docs/open_items.md)。

## 目录

```
config/          配置（default.yaml；本机覆盖写 local.yaml）
pc/tech12000/    电脑端 Python 程序
firmware/        wristband（XIAO ESP32-S3）与 receiver（ESP32-S3-DevKitC-1）固件，PlatformIO 工程
ios/             SwiftUI App 源码 + XcodeGen 工程描述
docs/            自定义协议、待确认事项
tests/           电脑端测试
```

## 在 Mac 上运行电脑端（无需任何硬件）

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -e ".[dev]"
```

```bash
.venv/bin/tech12000 run
```

浏览器打开 <http://127.0.0.1:8765>。界面上的"模拟剧本"按钮可以注入跌倒、挥手、慢蹲。

运行测试：

```bash
.venv/bin/pytest
```

回放一段录制（日志在 `data/sessions/` 下）：

```bash
.venv/bin/tech12000 replay data/sessions/<目录名>
```

## 安全设计要点

- 每次启动、每次复位都回到 **MONITOR**，不会自动使能。
- 进入 **ARMED** 需要：状态为 Ready、舵机驱动就绪、释放位置已配置、在本机界面手动输入确认。
- 使能、复位等控制只在 `127.0.0.1` 的操作员界面上提供；手机接口只读且需配对令牌。
- 每个事件有唯一 `event_id`；发舵机指令前先把执行记录落盘，同一事件重启后也不会再次执行；发送失败不自动重试。
- 必需数据源过期或断联即进入 Fault，不使用旧数据判断。
- 界面只显示"指令已发送"，实际展开状态始终为"未知／待检查"。

## 接入真实硬件

1. 固件：用 PlatformIO 打开 `firmware/receiver` 和 `firmware/wristband`。
   先烧 `wristband_sim` 环境验证 ESP-NOW 链路，再烧 `wristband` 环境接真实 IMU（接线见 `board_config.h`）。
   IMU 模块也可以先用 USB 直连电脑，用 `tech12000 imu-probe --port ...` 确认数据正常。
2. 接收板启动时会在串口打印自己的 MAC，填到手环的 `board_config.h`。
3. 查看串口设备名：

   ```bash
   .venv/bin/tech12000 ports
   ```

4. 新建 `config/local.yaml`：

   ```yaml
   sources:
     wristband:
       driver: serial
       port: /dev/cu.xxxxxxxx
   actuators:
     led:
       driver: receiver
   ```

## iOS App（手机提醒）

工程已经在仓库里，不需要装别的工具：

```bash
open ios/Tech12000.xcodeproj
```

1. Xcode 左侧点 `Tech12000` 工程 → Signing & Capabilities → Team 选自己的 Apple ID；Bundle Identifier 把 `com.example` 改成自己的（如 `com.你的名字.tech12000`）。
2. 顶部选自己的 iPhone（或模拟器），点 ▶ 运行。
3. 电脑上先 `tech12000 run`，用系统相机扫监控台上的二维码配对；App 弹出通知权限请求时点"允许"。

提醒方式：

- App 在前台：全屏告警 + 通知横幅和提示音。
- App 刚切到后台：系统给的几十秒内仍能收到并弹本地通知。
- App 被挂起、被划掉或锁屏较久：**收不到**。这要靠第二阶段的 APNs 推送。
- 与电脑断开超过 15 秒、或电脑端进入故障状态时，各提醒一次。

## 凭据

不要把 Apple 账号密码、APNs `.p8` 私钥提交到仓库。APNs 凭据只通过环境变量指向本地文件（见 `pc/tech12000/apns.py`）。
