// 亚博六轴 IMU 串口驱动（协议解析见 yb_imu_protocol.h）。
//   - 模块串口 115200 bps，默认 25 Hz 输出；上电后约 5 s 才就绪（模块介绍：启动时间 5000 ms）。
//   - 设置频率命令没有应答，所以开机后的前 IMU_RATE_RETRY_MS 内每秒重发一次，之后不再发。
//   - 帧内无时间戳：has_imu_time = false，时间以 XIAO 收齐该帧的时刻为准。
//   - 只用加速度和角速度（六轴）；磁力计、四元数、欧拉角帧解析后丢弃。
#ifndef IMU_SIM
#include <Arduino.h>
#include "esp_timer.h"
#include "board_config.h"
#include "imu_driver.h"
#include "yb_imu_protocol.h"

#if !defined(IMU_RX_PIN) || !defined(IMU_TX_PIN) || !defined(IMU_BAUD) || !defined(IMU_RATE_HZ)
#error "请在 board_config.h 中填写 IMU_RX_PIN / IMU_TX_PIN / IMU_BAUD / IMU_RATE_HZ"
#endif

#ifndef IMU_RATE_RETRY_MS
#define IMU_RATE_RETRY_MS 10000
#endif

static HardwareSerial &ImuSerial = Serial1;
static ybimu::Parser g_parser;
static uint32_t g_begin_ms = 0, g_last_rate_ms = 0;

static void send_set_rate() {
  uint8_t cmd[8];
  size_t n = ybimu::build_set_rate(IMU_RATE_HZ, cmd);
  if (n) ImuSerial.write(cmd, n);
}

bool imu_begin() {
  ImuSerial.begin(IMU_BAUD, SERIAL_8N1, IMU_RX_PIN, IMU_TX_PIN);
  g_begin_ms = millis();
  g_last_rate_ms = 0;
  return true;
}

bool imu_poll(ImuReading &out) {
  uint32_t now_ms = millis();
  if (now_ms - g_begin_ms < IMU_RATE_RETRY_MS && now_ms - g_last_rate_ms >= 1000) {
    g_last_rate_ms = now_ms;
    send_set_rate();
  }
  ybimu::Raw raw;
  while (ImuSerial.available() > 0) {
    if (g_parser.push((uint8_t)ImuSerial.read(), raw)) {
      for (int i = 0; i < 3; i++) {
        out.accel[i] = raw.accel_ms2[i];
        out.gyro[i] = raw.gyro_dps[i];
      }
      out.has_imu_time = false;
      out.imu_time_us = 0;
      out.t_rx_us = esp_timer_get_time();
      return true;   // 一次返回一帧；主循环会继续调用直到读空
    }
  }
  return false;
}

void imu_debug_print() {
  Serial.printf("imu frames=%lu csum_err=%lu other=%lu resync=%lu\n", (unsigned long)g_parser.frames,
                (unsigned long)g_parser.checksum_errors, (unsigned long)g_parser.other_frames,
                (unsigned long)g_parser.resyncs);
}
#endif
