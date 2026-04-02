#include "wifi_prov.h"

#include <ctype.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>

#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_system.h"

/* Fallback defaults for esp_wifi_remote when sdkconfig lacks these symbols */
#ifndef CONFIG_WIFI_RMT_STATIC_RX_BUFFER_NUM
#define CONFIG_WIFI_RMT_STATIC_RX_BUFFER_NUM 16
#endif
#ifndef CONFIG_WIFI_RMT_DYNAMIC_RX_BUFFER_NUM
#define CONFIG_WIFI_RMT_DYNAMIC_RX_BUFFER_NUM 64
#endif
#ifndef CONFIG_WIFI_RMT_DYNAMIC_TX_BUFFER_NUM
#define CONFIG_WIFI_RMT_DYNAMIC_TX_BUFFER_NUM 64
#endif
#ifndef CONFIG_WIFI_RMT_TX_BUFFER_TYPE
#define CONFIG_WIFI_RMT_TX_BUFFER_TYPE 0
#endif
#ifndef CONFIG_WIFI_RMT_DYNAMIC_RX_MGMT_BUF
#define CONFIG_WIFI_RMT_DYNAMIC_RX_MGMT_BUF 1
#endif
#ifndef CONFIG_WIFI_RMT_ESPNOW_MAX_ENCRYPT_NUM
#define CONFIG_WIFI_RMT_ESPNOW_MAX_ENCRYPT_NUM 7
#endif

/* CRITICAL: Use ESP-Hosted Remote WiFi API instead of standard esp_wifi.h */
#include "esp_wifi_remote.h"
#include "esp_wifi_default_config.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "freertos/timers.h"
#include "nvs.h"
#include "nvs_flash.h"

#define WIFI_PROV_NAMESPACE      "wifi"
#define WIFI_PROV_KEY_SSID       "ssid"
#define WIFI_PROV_KEY_PASS       "pass"
#define WIFI_PROV_AP_SSID        "O_Dien_Thong_Minh"
#define WIFI_FAILOVER_TIMEOUT_MS 15000

static const char *TAG = "wifi_prov";

static TimerHandle_t s_failover_timer;
static httpd_handle_t s_httpd = NULL;
static esp_netif_t *s_sta_netif = NULL;
static esp_netif_t *s_ap_netif = NULL;
static bool s_connected = false;

/* Callbacks to notify main app about WiFi events */
static wifi_connected_cb_t s_connected_cb = NULL;
static wifi_disconnected_cb_t s_disconnected_cb = NULL;

static esp_err_t wifi_switch_to_ap(void);

static esp_err_t nvs_load_credentials(char *ssid, size_t ssid_len, char *pass, size_t pass_len)
{
    nvs_handle_t handle;
    esp_err_t err = nvs_open(WIFI_PROV_NAMESPACE, NVS_READONLY, &handle);
    if (err != ESP_OK) {
        return err;
    }

    size_t ssid_required = ssid_len;
    size_t pass_required = pass_len;
    err = nvs_get_str(handle, WIFI_PROV_KEY_SSID, ssid, &ssid_required);
    if (err == ESP_OK) {
        err = nvs_get_str(handle, WIFI_PROV_KEY_PASS, pass, &pass_required);
    }

    nvs_close(handle);
    return err;
}

static esp_err_t nvs_save_credentials(const char *ssid, const char *pass)
{
    nvs_handle_t handle;
    esp_err_t err = nvs_open(WIFI_PROV_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "NVS open failed: %s", esp_err_to_name(err));
        return err;
    }

    err = nvs_set_str(handle, WIFI_PROV_KEY_SSID, ssid);
    if (err == ESP_OK) {
        err = nvs_set_str(handle, WIFI_PROV_KEY_PASS, pass);
    }
    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }

    nvs_close(handle);
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "Saved WiFi credentials to NVS");
    } else {
        ESP_LOGE(TAG, "Failed to save credentials: %s", esp_err_to_name(err));
    }
    return err;
}

static esp_err_t http_get_handler(httpd_req_t *req)
{
    const char *page =
        "<!DOCTYPE html><html><head><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<style>body{font-family:sans-serif;background:#f6f8fb;padding:24px;}"
        ".card{max-width:420px;margin:auto;background:#fff;padding:20px;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.08);}"
        "input{width:100%;padding:12px;margin:8px 0;border:1px solid #ccc;border-radius:8px;}"
        "button{width:100%;padding:12px;background:#0070f3;color:#fff;border:none;border-radius:8px;font-size:16px;cursor:pointer;}"
        "button:hover{background:#0059c1;}h2{text-align:center;}</style></head>"
        "<body><div class=\"card\"><h2>WiFi Setup</h2>"
        "<form method=\"POST\" action=\"/\">"
        "<input name=\"ssid\" placeholder=\"SSID\" required>"
        "<input name=\"pass\" placeholder=\"Password\" type=\"password\" required>"
        "<button type=\"submit\">Save & Restart</button>"
        "</form></div></body></html>";
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_sendstr(req, page);
}

static void url_decode(char *dst, const char *src)
{
    char a, b;
    while (*src) {
        if ((*src == '%') && ((a = src[1]) && (b = src[2])) && (isxdigit(a) && isxdigit(b))) {
            if (a >= 'a') a -= 'a' - 'A';
            if (a >= 'A') a -= ('A' - 10);
            else a -= '0';
            if (b >= 'a') b -= 'a' - 'A';
            if (b >= 'A') b -= ('A' - 10);
            else b -= '0';
            *dst++ = (char)(16 * a + b);
            src += 3;
        } else if (*src == '+') {
            *dst++ = ' ';
            src++;
        } else {
            *dst++ = *src++;
        }
    }
    *dst = '\0';
}

static void extract_field(const char *body, const char *key, char *out, size_t out_len)
{
    const char *p = strstr(body, key);
    if (!p) {
        out[0] = '\0';
        return;
    }
    p += strlen(key);
    const char *end = strchr(p, '&');
    size_t len = end ? (size_t)(end - p) : strlen(p);
    if (len >= out_len) {
        len = out_len - 1;
    }
    memcpy(out, p, len);
    out[len] = '\0';
    url_decode(out, out);
}

static esp_err_t http_post_handler(httpd_req_t *req)
{
    int total_len = req->content_len;
    if (total_len <= 0 || total_len > 512) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid content length");
        return ESP_FAIL;
    }

    char *buf = malloc(total_len + 1);
    if (!buf) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "No mem");
        return ESP_FAIL;
    }

    int received = 0;
    while (received < total_len) {
        int ret = httpd_req_recv(req, buf + received, total_len - received);
        if (ret <= 0) {
            free(buf);
            return ESP_FAIL;
        }
        received += ret;
    }
    buf[received] = '\0';

    char ssid[33];
    char pass[65];
    extract_field(buf, "ssid=", ssid, sizeof(ssid));
    extract_field(buf, "pass=", pass, sizeof(pass));
    free(buf);

    if (ssid[0] == '\0') {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "SSID missing");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Received new credentials: ssid='%s'", ssid);
    esp_err_t err = nvs_save_credentials(ssid, pass);
    if (err != ESP_OK) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Save failed");
        return ESP_FAIL;
    }

    httpd_resp_set_type(req, "text/html");
    httpd_resp_sendstr(req, "<!DOCTYPE html><html><body><h3>Da luu thanh cong, thiet bi dang khoi dong lai...</h3></body></html>");
    vTaskDelay(pdMS_TO_TICKS(2000));
    esp_restart();
    return ESP_OK;
}

static httpd_handle_t start_webserver(void)
{
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    config.lru_purge_enable = true;

    httpd_handle_t server = NULL;
    esp_err_t ret = httpd_start(&server, &config);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start httpd: %s", esp_err_to_name(ret));
        return NULL;
    }

    httpd_uri_t root_get = {
        .uri = "/",
        .method = HTTP_GET,
        .handler = http_get_handler,
        .user_ctx = NULL,
    };
    httpd_register_uri_handler(server, &root_get);

    httpd_uri_t root_post = {
        .uri = "/",
        .method = HTTP_POST,
        .handler = http_post_handler,
        .user_ctx = NULL,
    };
    httpd_register_uri_handler(server, &root_post);

    ESP_LOGI(TAG, "HTTP server started on 192.168.4.1");
    return server;
}

static void failover_timer_cb(TimerHandle_t xTimer)
{
    (void)xTimer;
    ESP_LOGW(TAG, "Failover timer expired, switching to AP mode");
    wifi_switch_to_ap();
}

static esp_err_t wifi_switch_to_ap(void)
{
    if (s_httpd) {
        return ESP_OK; /* Already in AP mode */
    }

    if (s_failover_timer) {
        xTimerStop(s_failover_timer, 0);
    }

    esp_wifi_remote_stop();

    if (!s_ap_netif) {
        s_ap_netif = esp_netif_create_default_wifi_ap();
    }

    wifi_config_t ap_cfg = { 0 };
    strcpy((char *)ap_cfg.ap.ssid, WIFI_PROV_AP_SSID);
    ap_cfg.ap.ssid_len = strlen(WIFI_PROV_AP_SSID);
    ap_cfg.ap.channel = 1;
    ap_cfg.ap.max_connection = 4;
    ap_cfg.ap.authmode = WIFI_AUTH_OPEN;

    ESP_ERROR_CHECK(esp_wifi_remote_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_remote_set_config(WIFI_IF_AP, &ap_cfg));
    ESP_ERROR_CHECK(esp_wifi_remote_start());

    ESP_LOGW(TAG, "Switched to AP mode, SSID='%s', connect to http://192.168.4.1", WIFI_PROV_AP_SSID);

    s_httpd = start_webserver();
    return ESP_OK;
}

static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data)
{
    (void)arg;
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        ESP_LOGI(TAG, "WiFi STA start, connecting");
        esp_wifi_remote_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *disc = (wifi_event_sta_disconnected_t *)event_data;
        ESP_LOGW(TAG, "STA disconnected, reason=%d", disc->reason);
        if (s_connected) {
            s_connected = false;
            /* Notify app that WiFi disconnected */
            if (s_disconnected_cb) {
                s_disconnected_cb();
            }
        }
        if (s_failover_timer) {
            xTimerStart(s_failover_timer, 0);
        }
        esp_wifi_remote_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *ip = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "Got IP: " IPSTR, IP2STR(&ip->ip_info.ip));
        s_connected = true;
        if (s_failover_timer) {
            xTimerStop(s_failover_timer, 0);
        }
        /* Notify app that WiFi connected */
        if (s_connected_cb) {
            s_connected_cb();
        }
    }
}

static esp_err_t wifi_start_sta(const char *ssid, const char *pass)
{
    if (!s_sta_netif) {
        s_sta_netif = esp_netif_create_default_wifi_sta();
    }

    wifi_config_t sta_cfg = { 0 };
    strlcpy((char *)sta_cfg.sta.ssid, ssid, sizeof(sta_cfg.sta.ssid));
    strlcpy((char *)sta_cfg.sta.password, pass, sizeof(sta_cfg.sta.password));
    sta_cfg.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    sta_cfg.sta.sae_pwe_h2e = WPA3_SAE_PWE_BOTH;

    ESP_ERROR_CHECK(esp_wifi_remote_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_remote_set_config(WIFI_IF_STA, &sta_cfg));

    if (s_failover_timer) {
        xTimerStart(s_failover_timer, 0);
    }

    ESP_ERROR_CHECK(esp_wifi_remote_start());
    ESP_LOGI(TAG, "Connecting to ssid='%s'", ssid);
    return ESP_OK;
}

esp_err_t wifi_prov_start(wifi_connected_cb_t connected_cb, wifi_disconnected_cb_t disconnected_cb)
{
    /* Store callbacks */
    s_connected_cb = connected_cb;
    s_disconnected_cb = disconnected_cb;

    ESP_ERROR_CHECK(nvs_flash_init());
    if (!s_failover_timer) {
        s_failover_timer = xTimerCreate("failover", pdMS_TO_TICKS(WIFI_FAILOVER_TIMEOUT_MS), pdFALSE, NULL, failover_timer_cb);
    }

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    /* CRITICAL: Use ESP-Hosted Remote WiFi API instead of local esp_wifi_init */
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_remote_init(&cfg));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL));

    char ssid[33] = {0};
    char pass[65] = {0};
    esp_err_t err = nvs_load_credentials(ssid, sizeof(ssid), pass, sizeof(pass));
    if (err == ESP_OK && ssid[0] != '\0') {
        ESP_LOGI(TAG, "Found stored credentials, attempting STA connect");
        wifi_start_sta(ssid, pass);
    } else {
        ESP_LOGW(TAG, "No stored credentials, starting AP provisioning");
        wifi_switch_to_ap();
    }

    return ESP_OK;
}

esp_err_t wifi_prov_erase_credentials(void)
{
    nvs_handle_t handle;
    esp_err_t err = nvs_open(WIFI_PROV_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "NVS open failed: %s", esp_err_to_name(err));
        return err;
    }

    err = nvs_erase_key(handle, WIFI_PROV_KEY_SSID);
    if (err == ESP_OK || err == ESP_ERR_NVS_NOT_FOUND) {
        err = nvs_erase_key(handle, WIFI_PROV_KEY_PASS);
    }
    if (err == ESP_OK || err == ESP_ERR_NVS_NOT_FOUND) {
        err = nvs_commit(handle);
    }

    nvs_close(handle);
    
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "WiFi credentials erased from NVS");
    } else {
        ESP_LOGE(TAG, "Failed to erase credentials: %s", esp_err_to_name(err));
    }
    
    return err;
}
