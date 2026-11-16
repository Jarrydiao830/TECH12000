// 手环板级配置。引脚、波特率必须按【实物引脚图 + 亚博六轴模块文档】填写，不要猜。
#pragma once

// ---- ESP-NOW ----
// 两端必须使用同一信道。固定端不连 Wi-Fi，信道由这里说了算。
#define ESPNOW_CHANNEL 1
// 固定端接收板的 MAC（接收板启动时会在串口打印）。
// 联调初期可用广播地址；确定后改成接收板的实际 MAC。
#define RECEIVER_MAC {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF}

// ---- IMU UART（IMU_SIM 构建不需要）----
// IMU TX -> XIAO RX，IMU RX -> XIAO TX。供电电压与串口电平按模块文档确认。
// #define IMU_RX_PIN  ?    // XIAO 上接 IMU TX 的 GPIO 编号
// #define IMU_TX_PIN  ?    // XIAO 上接 IMU RX 的 GPIO 编号
// #define IMU_BAUD    ?    // 模块文档给出的波特率
