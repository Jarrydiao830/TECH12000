// TECH12000 手环 -> 固定端 ESP-NOW 数据包定义（本项目自定义，两端固件共用）。
// 与电脑之间的串口行协议见 docs/protocol.md。
#pragma once
#include <stddef.h>
#include <stdint.h>

#define T12K_MAGIC 0x54C1
#define T12K_VERSION 1

// flags
#define T12K_FLAG_IMU_TIME_VALID 0x01  // t_imu_us 有效（IMU 模块自身提供采样时间戳时）
#define T12K_FLAG_SIMULATED 0x02       // 数据由固件模拟产生（IMU_SIM 构建）

typedef struct __attribute__((packed)) {
  uint16_t magic;
  uint8_t version;
  uint8_t flags;
  uint32_t device_id;   // 手环 MAC 低32位
  uint32_t session_id;  // 每次上电随机生成，用于区分重启前后的序号
  uint32_t seq;         // 每包 +1
  uint64_t t_mcu_us;    // XIAO 收齐这一帧 IMU 数据的本地时间（上电起算）
  uint64_t t_imu_us;    // IMU 自带的采样时间；无则为0且不置 IMU_TIME_VALID
  float accel[3];       // m/s^2，传感器坐标系
  float gyro[3];        // deg/s，传感器坐标系
  uint16_t crc16;       // CRC-16/CCITT-FALSE，覆盖本字段之前的所有字节
} t12k_imu_packet_t;

static inline uint16_t t12k_crc16(const uint8_t *d, size_t n) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < n; i++) {
    crc ^= (uint16_t)d[i] << 8;
    for (int b = 0; b < 8; b++) crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
  }
  return crc;
}
