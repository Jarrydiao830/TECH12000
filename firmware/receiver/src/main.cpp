// TECH12000 固定端固件：
//   ESP-NOW 收包 -> 校验/去重 -> 加接收时间 -> 每包一行 JSON 发给电脑
//   电脑 -> 一行 JSON 指令 -> LED
//   可选实体按钮 -> 上报事件（只上报，不在固件里做任何执行决定）
#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "esp_timer.h"

#include "board_config.h"
#include "protocol.h"

struct RxItem {
  t12k_imu_packet_t pkt;
  uint64_t t_rx_us;
  int8_t rssi;
  uint8_t len;
};

static QueueHandle_t g_q;
static volatile uint32_t g_overflow = 0;
static uint32_t g_rx = 0, g_bad = 0, g_crc = 0, g_dup = 0;
static uint32_t g_last_dev = 0, g_last_ses = 0, g_last_seq = 0;
static uint64_t g_last_rx_us = 0;
static uint32_t g_last_pc_ms = 0;
static bool g_pc_seen = false;

enum LedPattern { LED_INIT, LED_READY, LED_SUSPECT, LED_TRIGGERED, LED_FAULT };
static LedPattern g_led = LED_INIT;

// 回调在 Wi-Fi 任务里执行：只打时间戳、入队，不做串口输出
static void enqueue(const uint8_t *data, int len, int8_t rssi) {
  RxItem it;
  it.t_rx_us = esp_timer_get_time();
  it.rssi = rssi;
  it.len = (uint8_t)min(len, 255);
  memset(&it.pkt, 0, sizeof(it.pkt));
  memcpy(&it.pkt, data, min((size_t)len, sizeof(it.pkt)));
  if (xQueueSend(g_q, &it, 0) != pdTRUE) g_overflow++;  // 电脑没在读：丢新包并计数，不阻塞
}

#if ESP_ARDUINO_VERSION_MAJOR >= 3
static void on_recv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
  enqueue(data, len, info->rx_ctrl ? info->rx_ctrl->rssi : 0);
}
#else
static void on_recv(const uint8_t *mac, const uint8_t *data, int len) { enqueue(data, len, 0); }
#endif

static void led_write(int pin, bool on) {
  if (pin < 0) return;
  digitalWrite(pin, (on == (bool)LED_ACTIVE_HIGH) ? HIGH : LOW);
}

#ifdef LED_PIN_GREEN
static const int kGreen = LED_PIN_GREEN;
#else
static const int kGreen = -1;
#endif
#ifdef LED_PIN_YELLOW
static const int kYellow = LED_PIN_YELLOW;
#else
static const int kYellow = -1;
#endif
#ifdef LED_PIN_RED
static const int kRed = LED_PIN_RED;
#else
static const int kRed = -1;
#endif

static void led_update() {
  bool blink = (millis() / 250) % 2;
  LedPattern p = g_led;
  if (!g_pc_seen || millis() - g_last_pc_ms > PC_TIMEOUT_MS) p = LED_FAULT;
  led_write(kGreen, p == LED_READY);
  led_write(kYellow, p == LED_SUSPECT || (p == LED_INIT && blink));
  led_write(kRed, p == LED_TRIGGERED || (p == LED_FAULT && blink));
}

// 指令是电脑端 json.dumps 生成的紧凑单行，这里只做关键字匹配，不引入 JSON 库
static void handle_line(const char *s) {
  g_pc_seen = true;
  g_last_pc_ms = millis();
  if (!strstr(s, "\"t\":\"led\"")) return;
  if (strstr(s, "\"state\":\"ready\"")) g_led = LED_READY;
  else if (strstr(s, "\"state\":\"suspected_fall\"")) g_led = LED_SUSPECT;
  else if (strstr(s, "\"state\":\"triggered\"")) g_led = LED_TRIGGERED;
  else if (strstr(s, "\"state\":\"fault\"")) g_led = LED_FAULT;
  else g_led = LED_INIT;
}

static void poll_serial() {
  static char buf[160];
  static size_t n = 0;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      buf[n] = 0;
      if (n) handle_line(buf);
      n = 0;
    } else if (n < sizeof(buf) - 1) {
      buf[n++] = c;
    } else {
      n = 0;  // 超长行丢弃
    }
  }
}

static void poll_button() {
#ifdef BUTTON_PIN
  static bool last = true;
  static uint32_t t_change = 0;
  bool now = digitalRead(BUTTON_PIN);
  if (now != last && millis() - t_change > 30) {
    last = now;
    t_change = millis();
    Serial.printf("{\"t\":\"btn\",\"ev\":\"%s\",\"trx\":%llu}\n", now ? "release" : "press",
                  (unsigned long long)esp_timer_get_time());
  }
#endif
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  for (int pin : {kGreen, kYellow, kRed})
    if (pin >= 0) pinMode(pin, OUTPUT);
#ifdef BUTTON_PIN
  pinMode(BUTTON_PIN, INPUT_PULLUP);
#endif
  g_q = xQueueCreate(64, sizeof(RxItem));

  WiFi.mode(WIFI_STA);
  esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
  if (esp_now_init() != ESP_OK) {
    Serial.println("{\"t\":\"log\",\"msg\":\"esp_now_init failed\"}");
    delay(1000);
    ESP.restart();
  }
  esp_now_register_recv_cb(on_recv);
  uint8_t mac[6];
  esp_wifi_get_mac(WIFI_IF_STA, mac);
  Serial.printf("{\"t\":\"boot\",\"mac\":\"%02X:%02X:%02X:%02X:%02X:%02X\",\"ch\":%d,\"proto\":%d}\n",
                mac[0], mac[1], mac[2], mac[3], mac[4], mac[5], ESPNOW_CHANNEL, T12K_VERSION);
}

void loop() {
  RxItem it;
  while (xQueueReceive(g_q, &it, 0) == pdTRUE) {
    const t12k_imu_packet_t &p = it.pkt;
    if (it.len != sizeof(t12k_imu_packet_t) || p.magic != T12K_MAGIC || p.version != T12K_VERSION) {
      g_bad++;
      continue;
    }
    if (t12k_crc16((const uint8_t *)&p, offsetof(t12k_imu_packet_t, crc16)) != p.crc16) {
      g_crc++;
      continue;
    }
    if (p.device_id == g_last_dev && p.session_id == g_last_ses && p.seq == g_last_seq) {
      g_dup++;  // 链路层重传造成的重复包
      continue;
    }
    g_last_dev = p.device_id;
    g_last_ses = p.session_id;
    g_last_seq = p.seq;
    g_last_rx_us = it.t_rx_us;
    g_rx++;
    char ti[24] = "null";
    if (p.flags & T12K_FLAG_IMU_TIME_VALID) snprintf(ti, sizeof(ti), "%llu", (unsigned long long)p.t_imu_us);
    Serial.printf(
        "{\"t\":\"imu\",\"dev\":\"%08lx\",\"ses\":%lu,\"seq\":%lu,\"tm\":%llu,\"ti\":%s,\"trx\":%llu,"
        "\"a\":[%.4f,%.4f,%.4f],\"g\":[%.3f,%.3f,%.3f],\"f\":%u,\"rssi\":%d}\n",
        (unsigned long)p.device_id, (unsigned long)p.session_id, (unsigned long)p.seq,
        (unsigned long long)p.t_mcu_us, ti, (unsigned long long)it.t_rx_us,
        p.accel[0], p.accel[1], p.accel[2], p.gyro[0], p.gyro[1], p.gyro[2], p.flags, it.rssi);
  }

  static uint32_t last_hb = 0;
  if (millis() - last_hb >= 1000) {  // 设备在线状态上报（与人体心跳无关）
    last_hb = millis();
    long age = g_last_rx_us ? (long)((esp_timer_get_time() - g_last_rx_us) / 1000) : -1;
    Serial.printf("{\"t\":\"hb\",\"up_ms\":%lu,\"rx\":%lu,\"bad\":%lu,\"crc\":%lu,\"dup\":%lu,"
                  "\"ovf\":%lu,\"age_ms\":%ld}\n",
                  (unsigned long)millis(), (unsigned long)g_rx, (unsigned long)g_bad,
                  (unsigned long)g_crc, (unsigned long)g_dup, (unsigned long)g_overflow, age);
  }
  poll_serial();
  poll_button();
  led_update();
  delay(1);
}
