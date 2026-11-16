// 手环板级配置。引脚、波特率必须按【实物引脚图 + 亚博六轴模块文档】填写，不要猜。
#pragma once

// ---- ESP-NOW ----
// 两端必须使用同一信道。固定端不连 Wi-Fi，信道由这里说了算。
#define ESPNOW_CHANNEL 1
// 固定端接收板的 MAC（接收板启动时会在串口打印）。
// 联调初期可用广播地址；确定后改成接收板的实际 MAC。
#define RECEIVER_MAC {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF}

// ---- IMU UART（IMU_SIM 构建不需要）----
// 接线（本项目的选择，按此接线即可；要换引脚改这里）：
//   IMU TX -> XIAO D7（板上丝印 RX）    IMU RX -> XIAO D6（板上丝印 TX）
//   IMU GND -> XIAO GND                IMU 供电见 docs/open_items.md（XIAO 的 IO 只能接 3.3 V 电平）
#define IMU_RX_PIN  D7       // XIAO 上接 IMU TX 的引脚
#define IMU_TX_PIN  D6       // XIAO 上接 IMU RX 的引脚
#define IMU_BAUD    115200   // 《IMU模块介绍》基础参数：串口波特率 115200bps
#define IMU_RATE_HZ 100      // 协议允许 10~100 Hz，默认 25 Hz；开机后由固件下发
