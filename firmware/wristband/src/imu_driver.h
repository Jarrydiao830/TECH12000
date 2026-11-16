#pragma once
#include <stdint.h>

struct ImuReading {
  float accel[3];        // m/s^2
  float gyro[3];         // deg/s
  bool has_imu_time;     // 模块是否自带采样时间戳
  uint64_t imu_time_us;
  uint64_t t_rx_us;      // XIAO 收齐该帧的时间（esp_timer_get_time）
};

bool imu_begin();
// 非阻塞。解析出一帧完整数据返回 true。
bool imu_poll(ImuReading &out);
