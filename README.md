# TECH12000 浴室跌倒检测与气囊触发原型

固定式毫米波雷达 + 无线手环，电脑融合判断疑似跌倒，控制 LED 与舵机，并把状态推送到 iOS App。
不使用摄像头，不监测心率或呼吸。

**这是研究原型。** 跌倒检测、撞击前预测、气囊部署、缓冲效果是四个不同的验证目标；
"检测到并发出指令"不等于"气囊已展开"，更不等于"保护成功"。

## 当前进度

| 部分 | 状态 |
|---|---|
| 电脑端框架（采集/对齐/状态机/执行/日志/回放/界面/手机接口） | 可运行，模拟数据，23 项自动测试通过 |
| 接收板固件 | 已编译通过，未上板验证 |
| 手环固件（内置模拟 IMU） | 已编译通过，未上板验证 |
| 手环固件（真实 IMU） | **未实现**，等待亚博协议文档 |
| RS6240 雷达驱动 | **未实现**，等待官方 SDK/协议 |
| Hiwonder 舵机控制器驱动 | **未实现**，等待官方手册 |
| iOS App | 源码骨架，**未经 Xcode 编译** |
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
   先烧 `wristband_sim` 环境验证 ESP-NOW 链路，再实现真实 IMU 驱动。
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

## iOS App

```bash
brew install xcodegen
```

```bash
cd ios && xcodegen && open Tech12000.xcodeproj
```

在 Xcode 里选择自己的 Team 后运行到 iPhone。用系统相机扫电脑监控台上的二维码即可配对。
当前只有前台告警（App 打开时），不是锁屏推送。

## 凭据

不要把 Apple 账号密码、APNs `.p8` 私钥提交到仓库。APNs 凭据只通过环境变量指向本地文件（见 `pc/tech12000/apns.py`）。
