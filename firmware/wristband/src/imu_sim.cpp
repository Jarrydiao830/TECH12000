// 模拟 IMU：100 Hz，静止重力 + 少量噪声。只用于链路联调。
#ifdef IMU_SIM
#include <Arduino.h>
#include "esp_timer.h"
#include "imu_driver.h"

static uint64_t next_us = 0;

bool imu_begin() {
  next_us = esp_timer_get_time();
  return true;
}

bool imu_poll(ImuReading &out) {
  uint64_t now = esp_timer_get_time();
  if (now < next_us) return false;
  next_us += 10000;
  if (now > next_us + 50000) next_us = now;  // 落后太多就丢弃，不补发旧数据
  for (int i = 0; i < 3; i++) {
    out.accel[i] = ((int)(esp_random() % 200) - 100) / 1000.0f;
    out.gyro[i] = ((int)(esp_random() % 200) - 100) / 100.0f;
  }
  out.accel[2] += 9.81f;
  out.has_imu_time = false;
  out.imu_time_us = 0;
  out.t_rx_us = now;
  return true;
}
#endif
