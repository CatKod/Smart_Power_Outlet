#include <string.h>

#ifndef CONFIG_WIFI_RMT_STATIC_RX_BUFFER_NUM
#define CONFIG_WIFI_RMT_STATIC_RX_BUFFER_NUM 16
#define CONFIG_WIFI_RMT_DYNAMIC_RX_BUFFER_NUM 64
#define CONFIG_WIFI_RMT_TX_BUFFER_TYPE 0
#define CONFIG_WIFI_RMT_DYNAMIC_RX_MGMT_BUF 1
#define CONFIG_WIFI_RMT_ESPNOW_MAX_ENCRYPT_NUM 7
#endif

#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "nvs_flash.h"

// Simple Wi‑Fi station test for jc-esp32p4-m3 (ESP32-P4 + ESP32-C6).
// Replace the SSID/PASSWORD below with your AP credentials before building.

#define WIFI_SSID      "I2"
#define WIFI_PASSWORD  "abcd1232"
#define WIFI_MAX_RETRY 5

static EventGroupHandle_t s_wifi_event_group;
static int s_retry_count = 0;
static const int WIFI_CONNECTED_BIT = BIT0;
static const int WIFI_FAIL_BIT = BIT1;
static const char *TAG = "wifi-test";

static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data)
{
	if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
		esp_wifi_connect();
	} else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
		if (s_retry_count < WIFI_MAX_RETRY) {
			s_retry_count++;
			ESP_LOGI(TAG, "retry %d connecting to AP", s_retry_count);
			esp_wifi_connect();
		} else {
			xEventGroupSetBits(s_wifi_event_group, WIFI_FAIL_BIT);
		}
	} else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
		ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
		ESP_LOGI(TAG, "got IP: " IPSTR, IP2STR(&event->ip_info.ip));
		s_retry_count = 0;
		xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
	}
}

static void wifi_init_sta(void)
{
	s_wifi_event_group = xEventGroupCreate();

	ESP_ERROR_CHECK(esp_netif_init());
	ESP_ERROR_CHECK(esp_event_loop_create_default());
	esp_netif_t *sta_netif = esp_netif_create_default_wifi_sta();
    if (sta_netif == NULL) {
        ESP_LOGE(TAG, "Failed to create default WiFi STA interface");
        abort();
    }

	wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
	ESP_ERROR_CHECK(esp_wifi_init(&cfg));

	ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
	ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, NULL));

	wifi_config_t wifi_config = {
		.sta = {
			.ssid = WIFI_SSID,
			.password = WIFI_PASSWORD,
			.threshold.authmode = WIFI_AUTH_WPA2_PSK,
			.sae_pwe_h2e = WPA3_SAE_PWE_BOTH,
		},
	};

	ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
	ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
	ESP_ERROR_CHECK(esp_wifi_start());

	EventBits_t bits = xEventGroupWaitBits(
		s_wifi_event_group,
		WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
		pdFALSE,
		pdFALSE,
		portMAX_DELAY);

	if (bits & WIFI_CONNECTED_BIT) {
		ESP_LOGI(TAG, "connected to SSID:%s", WIFI_SSID);
	} else if (bits & WIFI_FAIL_BIT) {
		ESP_LOGE(TAG, "failed to connect to SSID:%s", WIFI_SSID);
	} else {
		ESP_LOGE(TAG, "unexpected event");
	}

	ESP_ERROR_CHECK(esp_event_handler_instance_unregister(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler));
	ESP_ERROR_CHECK(esp_event_handler_instance_unregister(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler));
	vEventGroupDelete(s_wifi_event_group);
}

void app_main(void)
{
	// NVS is needed for Wi‑Fi driver storage.
	ESP_ERROR_CHECK(nvs_flash_init());
	wifi_init_sta();
}
