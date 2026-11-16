// 亚博（Yahboom）高精度 IMU 串口协议解析。纯 C++，不依赖 Arduino，可在电脑上单独编译测试。
//
// 依据：imu/通信协议/通信协议.xlsx（串口通讯协议页）与厂家 YbImuLib/YbImuSerialLib.py：
//   帧 = 0x7E 0x23 LEN FUNC DATA... CHECKSUM
//   LEN = 整帧字节数（含帧头与校验）；CHECKSUM = 从帧头累加到校验前一字节，取低 8 位。
//   FUNC 0x04 原始数据：ACCEL_X/Y/Z, GYRO_X/Y/Z, MAG_X/Y/Z，各为 int16 小端，LEN = 0x17。
//     ACCEL 比例 16/32767 (g)，GYRO 比例 2000/32767 (°/s)；MAG 本项目不用（只按六轴处理）。
//   设置输出频率：7E 23 07 60 <Hz 10..100> 5F <sum>，无应答。
//   帧内没有采样时间戳。
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace ybimu {

constexpr uint8_t HEAD1 = 0x7E, HEAD2 = 0x23;
constexpr uint8_t FUNC_RAW = 0x04, FUNC_SET_RATE = 0x60;
constexpr uint8_t RAW_LEN = 0x17;
constexpr uint8_t MAX_LEN = 40;          // 与厂家库 _RX_MAX_LEN 一致
constexpr float ACCEL_G_PER_LSB = 16.0f / 32767.0f;
constexpr float GYRO_DPS_PER_LSB = 2000.0f / 32767.0f;
constexpr float STANDARD_G = 9.80665f;   // g -> m/s^2 的换算常数（本项目选择的定义）

struct Raw {
  float accel_ms2[3];
  float gyro_dps[3];
};

inline uint8_t checksum(const uint8_t *p, size_t n) {
  uint32_t s = 0;
  for (size_t i = 0; i < n; i++) s += p[i];
  return (uint8_t)(s & 0xFF);
}

// 组"设置输出频率"命令，out 至少 7 字节；hz 超出 10..100 返回 0（不发送）。
inline size_t build_set_rate(uint8_t hz, uint8_t *out) {
  if (hz < 10 || hz > 100) return 0;
  out[0] = HEAD1; out[1] = HEAD2; out[2] = 7; out[3] = FUNC_SET_RATE; out[4] = hz; out[5] = 0x5F;
  out[6] = checksum(out, 6);
  return 7;
}

class Parser {
 public:
  uint32_t frames = 0, checksum_errors = 0, other_frames = 0, resyncs = 0;

  // 逐字节输入。解析出一帧 0x04 原始数据时返回 true 并填写 out。
  bool push(uint8_t b, Raw &out) {
    switch (n_) {
      case 0:
        if (b == HEAD1) buf_[n_++] = b; else resyncs++;
        return false;
      case 1:
        if (b == HEAD2) { buf_[n_++] = b; }
        else { n_ = 0; resyncs++; if (b == HEAD1) buf_[n_++] = b; }
        return false;
      case 2:
        if (b < 5 || b > MAX_LEN) { n_ = 0; resyncs++; return false; }
        buf_[n_++] = b;
        return false;
      default:
        buf_[n_++] = b;
        if (n_ < buf_[2]) return false;
        size_t len = n_;
        n_ = 0;
        if (checksum(buf_, len - 1) != buf_[len - 1]) { checksum_errors++; return false; }
        frames++;
        if (buf_[3] != FUNC_RAW || len != RAW_LEN) { other_frames++; return false; }
        const uint8_t *d = &buf_[4];
        for (int i = 0; i < 3; i++) {
          out.accel_ms2[i] = (float)rd16(d + 2 * i) * ACCEL_G_PER_LSB * STANDARD_G;
          out.gyro_dps[i] = (float)rd16(d + 6 + 2 * i) * GYRO_DPS_PER_LSB;
        }
        return true;
    }
  }

 private:
  static int16_t rd16(const uint8_t *p) { return (int16_t)(uint16_t)(p[0] | (p[1] << 8)); }
  uint8_t buf_[MAX_LEN] = {};
  size_t n_ = 0;
};

}  // namespace ybimu
