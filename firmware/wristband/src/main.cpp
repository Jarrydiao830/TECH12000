// TECH12000 手环固件：读 IMU -> 打包 -> ESP-NOW 立即发送（失败即丢，不排队补发旧数据）。
#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "esp_timer.h"

#include "board_config.h"
#include "imu_driver.h"
#include "protocol.h"

static const uint8_t kPeer[6] = RECEIVER_MAC;
static uint32_t g_device_id, g_session_id, g_seq = 0;
static uint32_t g_send_fail = 0;

void setup() {
  Serial.begin(115200);  // 仅调试用
  WiFi.mode(WIFI_STA);
  esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);

  uint8_t mac[6];
  esp_wifi_get_mac(WIFI_IF_STA, mac);
  g_device_id = ((uint32_t)mac[2] << 24) | ((uint32_t)mac[3] << 16) | ((uint32_t)mac[4] << 8) | mac[5];
  g_session_id = esp_random();

  if (esp_now_init() != ESP_OK) {
    Serial.println("esp_now_init failed");
    delay(1000);
    ESP.restart();
  }
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, kPeer, 6);
  peer.channel = ESPNOW_CHANNEL;
  peer.encrypt = false;
  esp_now_add_peer(&peer);

  if (!imu_begin()) Serial.println("imu_begin failed");
  Serial.printf("wristband dev=%08lx ses=%lu ch=%d\n", (unsigned long)g_device_id,
                (unsigned long)g_session_id, ESPNOW_CHANNEL);
}

void loop() {
  ImuReading r;
  while (imu_poll(r)) {
    t12k_imu_packet_t p = {};
    p.magic = T12K_MAGIC;
    p.version = T12K_VERSION;
    p.flags = (r.has_imu_time ? T12K_FLAG_IMU_TIME_VALID : 0);
#ifdef IMU_SIM
    p.flags |= T12K_FLAG_SIMULATED;
#endif
    p.device_id = g_device_id;
    p.session_id = g_session_id;
    p.seq = ++g_seq;
    p.t_mcu_us = r.t_rx_us;
    p.t_imu_us = r.has_imu_time ? r.imu_time_us : 0;
    memcpy(p.accel, r.accel, sizeof(p.accel));
    memcpy(p.gyro, r.gyro, sizeof(p.gyro));
    p.crc16 = t12k_crc16((const uint8_t *)&p, offsetof(t12k_imu_packet_t, crc16));
    if (esp_now_send(kPeer, (const uint8_t *)&p, sizeof(p)) != ESP_OK) g_send_fail++;
  }
  // 注意：本硬件没有电池测量线路，因此不上报电量。
  delay(1);
}
