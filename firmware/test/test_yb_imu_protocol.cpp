// 电脑上编译运行：c++ -std=c++17 -I wristband/src test/test_yb_imu_protocol.cpp -o /tmp/t && /tmp/t
#include <cassert>
#include <cmath>
#include <cstdio>
#include <vector>
#include "yb_imu_protocol.h"
using namespace ybimu;

static std::vector<uint8_t> raw_frame(const int16_t v[9]) {
  std::vector<uint8_t> f = {HEAD1, HEAD2, RAW_LEN, FUNC_RAW};
  for (int i = 0; i < 9; i++) { f.push_back((uint8_t)(v[i] & 0xFF)); f.push_back((uint8_t)((uint16_t)v[i] >> 8)); }
  f.push_back(checksum(f.data(), f.size()));
  return f;
}

int main() {
  // 协议表示例：请求固件版本 7E 23 07 80 01 00 29；重置用户数据 7E 23 07 A0 01 5F A8
  const uint8_t ver[] = {0x7E, 0x23, 0x07, 0x80, 0x01, 0x00};
  assert(checksum(ver, 6) == 0x29);
  const uint8_t rst[] = {0x7E, 0x23, 0x07, 0xA0, 0x01, 0x5F};
  assert(checksum(rst, 6) == 0xA8);

  uint8_t cmd[8];
  assert(build_set_rate(100, cmd) == 7 && cmd[3] == 0x60 && cmd[4] == 100 && cmd[5] == 0x5F);
  assert(cmd[6] == checksum(cmd, 6));
  assert(build_set_rate(5, cmd) == 0 && build_set_rate(101, cmd) == 0);

  // 1 g 在 z 轴：raw = 32767/16 ≈ 2048；陀螺 x = -32767 -> -2000 °/s
  const int16_t v[9] = {0, 0, 2048, -32767, 0, 100, 1, 2, 3};
  auto f = raw_frame(v);
  // 前面混入垃圾、一个校验错误的帧、一个四元数帧（0x16，应被忽略）
  std::vector<uint8_t> s = {0x00, 0x7E, 0x11, 0x23};
  auto bad = f; bad.back() ^= 0xFF; s.insert(s.end(), bad.begin(), bad.end());
  std::vector<uint8_t> q = {HEAD1, HEAD2, 0x15, 0x16}; q.resize(0x14, 0x00); q.push_back(checksum(q.data(), q.size()));
  s.insert(s.end(), q.begin(), q.end());
  s.insert(s.end(), f.begin(), f.end());

  Parser p; Raw r; int got = 0;
  for (uint8_t b : s) if (p.push(b, r)) got++;
  assert(got == 1);
  assert(p.checksum_errors == 1 && p.other_frames == 1);
  assert(std::fabs(r.accel_ms2[2] - 2048 * 16.0f / 32767.0f * 9.80665f) < 1e-4);
  assert(std::fabs(r.accel_ms2[2] - 9.80665f) < 0.01f);
  assert(std::fabs(r.gyro_dps[0] + 2000.0f) < 1e-3);
  assert(std::fabs(r.gyro_dps[2] - 100 * 2000.0f / 32767.0f) < 1e-4);
  std::printf("yb_imu_protocol: all tests passed\n");
  return 0;
}
