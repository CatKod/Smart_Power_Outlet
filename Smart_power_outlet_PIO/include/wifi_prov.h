/**
 * @file wifi_prov.h
 * @brief WiFi Provisioning module
 *
 * Logic:
 *   1. Đọc SSID/pass từ Preferences (NVS). Nếu có → thử kết nối STA.
 *   2. Nếu kết nối thất bại sau WIFI_FAILOVER_TIMEOUT_MS → chuyển sang AP mode.
 *   3. AP mode phát SSID "O_Dien_Thong_Minh", Captive Portal tại 192.168.4.1.
 *   4. Người dùng nhập SSID/pass → lưu NVS → restart.
 *   5. Hàm wifi_prov_erase() xoá credentials NVS.
 */
#pragma once

#include <Arduino.h>
#include <functional>

#if !defined(SMART_OUTLET_ESP8266) && (defined(BOARD_ESP8266) || defined(ARDUINO_ARCH_ESP8266))
#define SMART_OUTLET_ESP8266 1
#endif

#ifdef SMART_OUTLET_ESP8266
// ESP8266 dùng EEPROM giả lập, cần thống nhất layout giữa các module
#define ESP8266_EEPROM_SIZE          512
#define ESP8266_EEPROM_WIFI_OFFSET   0
#define ESP8266_EEPROM_WIFI_MAGIC    0xA1B2C3D4
#define ESP8266_EEPROM_RELAY_OFFSET  256
#define ESP8266_EEPROM_RELAY_MAGIC   0x5A5AA55A
#endif

/** Thời gian timeout khi kết nối STA thất bại trước khi switch sang AP */
#define WIFI_FAILOVER_TIMEOUT_MS 15000

/** SSID của AP provisioning */
#define WIFI_PROV_AP_SSID "O_Dien_Thong_Minh"

/** Namespace Preferences cho WiFi credentials */
#define WIFI_PROV_NAMESPACE "wifi"

typedef std::function<void()> wifi_connected_cb_t;
typedef std::function<void()> wifi_disconnected_cb_t;

/**
 * @brief Khởi động WiFi provisioning.
 *
 * Gọi trong setup(). Hàm không blocking — trạng thái kết nối được
 * theo dõi bằng cách gọi wifi_prov_loop() mỗi vòng loop().
 *
 * @param connected_cb    Callback gọi khi WiFi STA kết nối thành công (IP có)
 * @param disconnected_cb Callback gọi khi WiFi STA mất kết nối
 */
void wifi_prov_start(wifi_connected_cb_t connected_cb,
                     wifi_disconnected_cb_t disconnected_cb);

/**
 * @brief Gọi trong loop() để xử lý sự kiện WiFiManager và failover timer.
 */
void wifi_prov_loop();

/**
 * @brief Xoá WiFi credentials khỏi Preferences (NVS).
 */
void wifi_prov_erase_credentials();

/**
 * @brief Trả về true nếu đang kết nối WiFi STA và có IP.
 */
bool wifi_prov_is_connected();
