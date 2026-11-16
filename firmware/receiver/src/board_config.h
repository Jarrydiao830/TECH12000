// 固定端板级配置。GPIO 必须按【实物引脚图和实际接线】填写，不要猜。
#pragma once

#define ESPNOW_CHANNEL 1       // 必须与手环一致
#define SERIAL_BAUD 921600     // 必须与电脑端 sources.wristband.baud 一致（原生USB CDC会忽略）

// ---- LED（可选；未定义的不驱动）。每个LED必须串限流电阻 ----
// #define LED_PIN_GREEN  ?
// #define LED_PIN_YELLOW ?
// #define LED_PIN_RED    ?
#define LED_ACTIVE_HIGH 1

// ---- 实体按钮（可选，瞬时按钮，按下接地，使用内部上拉）----
// #define BUTTON_PIN ?

// 超过这么久没收到电脑的任何指令，LED 转为故障闪烁（电脑程序可能已退出）
#define PC_TIMEOUT_MS 3000
