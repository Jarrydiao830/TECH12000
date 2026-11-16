// 亚博六轴 IMU 串口驱动 —— 未实现，等待该模块的准确型号与官方协议文档。
// 故意不写任何帧格式。实现时需要从文档确认：
//   1. 波特率、帧头、帧长、校验方式；输出频率如何配置（目标约100 Hz）。
//   2. 加速度/角速度的原始量纲与量程 -> 换算成 m/s^2 和 deg/s。
//   3. 帧内是否带时间戳（决定 has_imu_time）。
//   4. 供电电压和 TX/RX 电平是否与 XIAO 的 3.3 V IO 直接兼容。
//   5. 只使用加速度计 + 陀螺仪；姿态角/四元数仅在模块确实输出时再加。
#ifndef IMU_SIM
#include "board_config.h"
#include "imu_driver.h"

#if !defined(IMU_RX_PIN) || !defined(IMU_TX_PIN) || !defined(IMU_BAUD)
#error "请先在 board_config.h 中按实物和文档填写 IMU_RX_PIN / IMU_TX_PIN / IMU_BAUD"
#endif
#error "imu_yahboom.cpp 尚未实现：需要亚博六轴 IMU 的官方协议文档。链路联调请用 wristband_sim 环境。"

bool imu_begin() { return false; }
bool imu_poll(ImuReading &) { return false; }
#endif
