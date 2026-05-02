/**
 * @file wifi_prov.cpp
 * @brief WiFi Provisioning implementation (Arduino framework)
 *
 * Port từ wifi_prov.c (ESP-IDF) sang Arduino thuần.
 * Logic giữ nguyên:
 *   1. Đọc SSID/pass từ Preferences (NVS). Nếu có → kết nối STA.
 *   2. Timeout 15s chưa có IP → chuyển sang AP mode (Captive Portal).
 *   3. AP phát SSID "O_Dien_Thong_Minh", WebServer tại 192.168.4.1.
 *   4. Người dùng nhập SSID/pass → lưu Preferences → restart.
 *   5. wifi_prov_erase_credentials() xoá Preferences → restart.
 */

#include "wifi_prov.h"
#include "debug_log.h"

#include <DNSServer.h>
#ifdef SMART_OUTLET_ESP8266
#include <EEPROM.h>
#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#else
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#endif

// -----------------------------------------------------------------------
// Internal state
// -----------------------------------------------------------------------
static wifi_connected_cb_t    s_connected_cb    = nullptr;
static wifi_disconnected_cb_t s_disconnected_cb = nullptr;

#ifndef SMART_OUTLET_ESP8266
static Preferences  s_prefs;
#endif
#ifdef SMART_OUTLET_ESP8266
static ESP8266WebServer s_server(80);
#else
static WebServer    s_server(80);
#endif
static DNSServer    s_dns;

static bool          s_connected        = false;
static bool          s_ap_mode          = false;
static bool          s_has_credentials  = false;
static unsigned long s_connect_start_ms = 0;

static const char *PREF_KEY_SSID = "ssid";
static const char *PREF_KEY_PASS = "pass";

#ifdef SMART_OUTLET_ESP8266
static bool s_eeprom_ready = false;

static void ensure_eeprom_ready()
{
    if (!s_eeprom_ready) {
        EEPROM.begin(ESP8266_EEPROM_SIZE);
        s_eeprom_ready = true;
    }
}
#endif

// -----------------------------------------------------------------------
// Provisioning HTML page (giống ESP-IDF gốc)
// -----------------------------------------------------------------------
static const char PROV_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta charset="utf-8">
  <title>Smart Power Outlet - WiFi Setup</title>
  <style>
    body { font-family: sans-serif; background: #f6f8fb; padding: 24px; }
    .card { max-width: 420px; margin: auto; background: #fff;
            padding: 20px; border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
    h2 { text-align: center; color: #333; }
    input { width: 100%; padding: 12px; margin: 8px 0;
            border: 1px solid #ccc; border-radius: 8px;
            box-sizing: border-box; }
    button { width: 100%; padding: 12px; background: #0070f3;
             color: #fff; border: none; border-radius: 8px;
             font-size: 16px; cursor: pointer; }
    button:hover { background: #0059c1; }
  </style>
</head>
<body>
  <div class="card">
    <h2>&#128268; WiFi Setup</h2>
    <form method="POST" action="/">
      <input name="ssid" placeholder="SSID (Tên WiFi)" required>
      <input name="pass" placeholder="Password" type="password">
      <button type="submit">Lưu &amp; Kết nối</button>
    </form>
  </div>
</body>
</html>
)rawliteral";

static const char SAVED_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;text-align:center;padding:40px;">
  <h3>&#10003; Đã lưu thành công!</h3>
  <p>Thiết bị đang khởi động lại và kết nối WiFi...</p>
</body>
</html>
)rawliteral";

// -----------------------------------------------------------------------
// Helpers: Preferences (NVS)
// -----------------------------------------------------------------------

static bool prefs_load_credentials(char *ssid, size_t ssid_len,
                                   char *pass, size_t pass_len)
{
#ifdef SMART_OUTLET_ESP8266
    struct WifiCreds {
        uint32_t magic;
        char ssid[33];
        char pass[65];
    } creds = {0};

    ensure_eeprom_ready();
    EEPROM.get(ESP8266_EEPROM_WIFI_OFFSET, creds);

    if (creds.magic != ESP8266_EEPROM_WIFI_MAGIC || creds.ssid[0] == '\0') {
        return false;
    }

    strlcpy(ssid, creds.ssid, ssid_len);
    strlcpy(pass, creds.pass, pass_len);
    LOGF("[wifi_prov] Loaded credentials: ssid='%s'\n", ssid);
    return true;
#else
    s_prefs.begin(WIFI_PROV_NAMESPACE, /*readOnly=*/ true);
    String stored_ssid = s_prefs.getString(PREF_KEY_SSID, "");
    String stored_pass = s_prefs.getString(PREF_KEY_PASS, "");
    s_prefs.end();

    if (stored_ssid.length() == 0) {
        return false;
    }

    strlcpy(ssid, stored_ssid.c_str(), ssid_len);
    strlcpy(pass, stored_pass.c_str(), pass_len);
    LOGF("[wifi_prov] Loaded credentials: ssid='%s'\n", ssid);
    return true;
#endif
}

static void prefs_save_credentials(const char *ssid, const char *pass)
{
#ifdef SMART_OUTLET_ESP8266
    struct WifiCreds {
        uint32_t magic;
        char ssid[33];
        char pass[65];
    } creds = {0};

    creds.magic = ESP8266_EEPROM_WIFI_MAGIC;
    strlcpy(creds.ssid, ssid, sizeof(creds.ssid));
    strlcpy(creds.pass, pass, sizeof(creds.pass));

    ensure_eeprom_ready();
    EEPROM.put(ESP8266_EEPROM_WIFI_OFFSET, creds);
    EEPROM.commit();
    LOGF("[wifi_prov] Saved credentials: ssid='%s'\n", ssid);
#else
    s_prefs.begin(WIFI_PROV_NAMESPACE, /*readOnly=*/ false);
    s_prefs.putString(PREF_KEY_SSID, ssid);
    s_prefs.putString(PREF_KEY_PASS, pass);
    s_prefs.end();
    LOGF("[wifi_prov] Saved credentials: ssid='%s'\n", ssid);
#endif
}

// -----------------------------------------------------------------------
// HTTP Handlers for Captive Portal
// -----------------------------------------------------------------------

static void http_handle_get()
{
#ifdef SMART_OUTLET_ESP8266
    s_server.send_P(200, "text/html", PROV_HTML);
#else
    s_server.send(200, "text/html", PROV_HTML);
#endif
}

static void http_handle_post()
{
    String ssid = s_server.arg("ssid");
    String pass = s_server.arg("pass");

    if (ssid.length() == 0) {
        s_server.send(400, "text/plain", "SSID missing");
        return;
    }

    LOGF("[wifi_prov] Received new credentials: ssid='%s'\n", ssid.c_str());
    prefs_save_credentials(ssid.c_str(), pass.c_str());

#ifdef SMART_OUTLET_ESP8266
    s_server.send_P(200, "text/html", SAVED_HTML);
#else
    s_server.send(200, "text/html", SAVED_HTML);
#endif
    delay(2000);
    ESP.restart();
}

/** Redirect mọi request về trang provisioning (Captive Portal) */
static void http_handle_captive()
{
    s_server.sendHeader("Location", "http://192.168.4.1/", true);
    s_server.send(302, "text/plain", "");
}

static void start_webserver()
{
    s_server.on("/", HTTP_GET,  http_handle_get);
    s_server.on("/", HTTP_POST, http_handle_post);
    // Captive portal: redirect Android / iOS detection URLs
    s_server.onNotFound(http_handle_captive);
    s_server.begin();
    LOGLN("[wifi_prov] HTTP server started at 192.168.4.1");
}

// -----------------------------------------------------------------------
// Switch to AP (Captive Portal) mode
// -----------------------------------------------------------------------
static void switch_to_ap_mode()
{
    if (s_ap_mode) {
        return;  // Đã ở AP mode
    }

    LOGF("[wifi_prov] Switching to AP mode, SSID='%s'...\n",
                  WIFI_PROV_AP_SSID);

#ifdef SMART_OUTLET_ESP8266
    WiFi.disconnect();
#else
    WiFi.disconnect(true);
#endif
    delay(100);
    WiFi.mode(WIFI_AP);
    WiFi.softAP(WIFI_PROV_AP_SSID);  // Open AP, không cần password

    // DNS Server: redirect mọi domain về 192.168.4.1 (Captive Portal)
    s_dns.start(53, "*", WiFi.softAPIP());

    start_webserver();
    s_ap_mode = true;

    LOGF("[wifi_prov] AP active. Connect to '%s' then visit http://192.168.4.1\n",
                  WIFI_PROV_AP_SSID);
}

// -----------------------------------------------------------------------
// Public API
// -----------------------------------------------------------------------

void wifi_prov_start(wifi_connected_cb_t connected_cb,
                     wifi_disconnected_cb_t disconnected_cb)
{
    s_connected_cb    = connected_cb;
    s_disconnected_cb = disconnected_cb;

    char ssid[33] = {0};
    char pass[65] = {0};
    s_has_credentials = prefs_load_credentials(ssid, sizeof(ssid),
                                                pass, sizeof(pass));

    if (s_has_credentials) {
        LOGF("[wifi_prov] Found credentials, connecting to '%s'...\n", ssid);
        WiFi.mode(WIFI_STA);
        WiFi.begin(ssid, pass);
        s_connect_start_ms = millis();
        s_ap_mode = false;
    } else {
        LOGLN("[wifi_prov] No credentials stored, starting AP...");
        switch_to_ap_mode();
    }
}

void wifi_prov_loop()
{
    // --- STA mode: đang kết nối hoặc đã kết nối ---
    if (s_has_credentials && !s_ap_mode) {
        if (WiFi.status() == WL_CONNECTED) {
            if (!s_connected) {
                // Vừa kết nối thành công
                s_connected = true;
                LOGF("[wifi_prov] Connected! IP: %s\n",
                              WiFi.localIP().toString().c_str());
                if (s_connected_cb) {
                    s_connected_cb();
                }
            }
        } else {
            if (s_connected) {
                // Vừa mất kết nối
                s_connected = false;
                LOGLN("[wifi_prov] Disconnected! Attempting reconnect...");
                if (s_disconnected_cb) {
                    s_disconnected_cb();
                }
                WiFi.reconnect();
                s_connect_start_ms = millis();  // Reset failover timer
            } else {
                // Chưa có IP bao giờ → kiểm tra failover timeout
                unsigned long elapsed = millis() - s_connect_start_ms;
                if (elapsed >= WIFI_FAILOVER_TIMEOUT_MS) {
                    LOGLN("[wifi_prov] Connection timeout! Switching to AP...");
                    switch_to_ap_mode();
                }
            }
        }
    }

    // --- AP mode: xử lý DNS + HTTP (Captive Portal) ---
    if (s_ap_mode) {
        s_dns.processNextRequest();
        s_server.handleClient();
    }
}

void wifi_prov_erase_credentials()
{
    LOGLN("[wifi_prov] Erasing WiFi credentials from storage...");
#ifdef SMART_OUTLET_ESP8266
    struct WifiCreds {
        uint32_t magic;
        char ssid[33];
        char pass[65];
    } creds = {0};

    ensure_eeprom_ready();
    EEPROM.put(ESP8266_EEPROM_WIFI_OFFSET, creds);
    EEPROM.commit();
#else
    s_prefs.begin(WIFI_PROV_NAMESPACE, /*readOnly=*/ false);
    s_prefs.remove(PREF_KEY_SSID);
    s_prefs.remove(PREF_KEY_PASS);
    s_prefs.end();
#endif
    LOGLN("[wifi_prov] Credentials erased.");
}

bool wifi_prov_is_connected()
{
    return s_connected && (WiFi.status() == WL_CONNECTED);
}
