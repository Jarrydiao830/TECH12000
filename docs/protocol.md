# 本项目自定义的接口协议

这里只描述**本项目自己定义**的协议。IMU、雷达、舵机控制器的厂家协议不在此列，以官方文档为准。

## 1. 手环 → 固定端（ESP-NOW）

二进制定长包，定义见 `firmware/common/protocol.h` 的 `t12k_imu_packet_t`（小端，packed）。

| 字段 | 说明 |
|---|---|
| magic / version | `0x54C1` / `1` |
| flags | bit0 `t_imu_us` 有效；bit1 固件模拟数据 |
| device_id | 手环 MAC 低32位 |
| session_id | 每次上电随机生成 |
| seq | 每包 +1 |
| t_mcu_us | XIAO 收齐该帧 IMU 数据的本地时间 |
| t_imu_us | IMU 自带采样时间（模块不提供则无效） |
| accel[3] | m/s²，传感器坐标系 |
| gyro[3] | °/s，传感器坐标系 |
| crc16 | CRC-16/CCITT-FALSE |

发送失败即丢弃，不排队补发。没有电池测量线路，所以没有电量字段。

## 2. 固定端 → 电脑（USB 串口）

每行一个 JSON 对象，`\n` 结尾。不以 `{` 开头的行（如启动日志）只写入原始日志。

```json
{"t":"boot","mac":"AA:BB:CC:DD:EE:FF","ch":1,"proto":1}
{"t":"imu","dev":"a1b2c3d4","ses":123,"seq":42,"tm":1234567,"ti":null,"trx":2345678,"a":[0.1,0.0,9.8],"g":[0.5,0.1,0.0],"f":0,"rssi":-45}
{"t":"hb","up_ms":60000,"rx":5990,"bad":0,"crc":0,"dup":2,"ovf":0,"age_ms":8}
{"t":"btn","ev":"press","trx":3456789}
```

- `tm` 手环时钟、`trx` 接收板时钟，二者与电脑时钟互不相同，只能各自与同源时间比较。
- `hb` 是设备在线状态上报，与人体心跳无关。`ovf` 为接收队列溢出丢包数。
- `rssi` 在旧版 Arduino-ESP32 内核上恒为 0（回调不提供该信息）。

## 3. 电脑 → 固定端

```json
{"t":"led","state":"ready","mode":"monitor"}
```

`state` 取 `initializing / ready / suspected_fall / triggered / fault`。
接收板超过 `PC_TIMEOUT_MS` 没收到任何指令时，LED 自动转为故障闪烁。

## 4. 电脑 → 手机（局域网 HTTP / WebSocket）

所有请求带 `Authorization: Bearer <配对令牌>`。只读，没有任何控制接口。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/status` | 最新状态 |
| GET | `/api/v1/events?limit=20` | 事件历史 |
| GET | `/api/v1/events/{event_id}` | 单个事件 |
| POST | `/api/v1/apns/token` | 登记 APNs device token（第二阶段使用） |
| WS | `/api/v1/ws` | `{"type":"status",...}` 定时与变化时推送；`{"type":"event","event":{...}}` |

事件对象含 `event_id`、`t_wall`（原始发生时间）、`mode`、`deploy_status`、`deploy_outcome`（恒为 `unknown_check_required`）、`is_test`、`message`。App 按 `event_id` 去重。

配对二维码内容：`tech12000://pair?host=<电脑IP>&port=<端口>&token=<令牌>`。
