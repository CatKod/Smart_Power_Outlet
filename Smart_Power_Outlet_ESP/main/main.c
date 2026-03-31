/*
 * Smart Power Outlet - ESP32-P4 (Host) + ESP32-C6 (Co-processor via ESP-Hosted)
 * Features: WiFi Captive Portal Provisioning, MQTT control, relay on GPIO20
 */

#include <assert.h>
#include <string.h>
#include "nvs_flash.h"
#include "nvs.h"

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

#include "driver/gpio.h"
#include "esp_event.h"
#include "esp_hosted.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_wifi_remote.h"

#include "mqtt_client.h"
#include "wifi_prov.h"

#define MQTT_URI            "mqtt://broker.hivemq.com:1883"
#define MQTT_TOPIC_CMD      "home/socket/cmd"
#define MQTT_TOPIC_STATUS   "home/socket/status"
#define RELAY_GPIO          GPIO_NUM_20

typedef enum {
	RELAY_CMD_ON = 0,
	RELAY_CMD_OFF,
} relay_cmd_t;

static const char *TAG = "smart_socket";
static QueueHandle_t s_relay_queue;
static esp_mqtt_client_handle_t s_mqtt_client;

static void relay_gpio_init(void)
{
	gpio_config_t io_conf = {
		.pin_bit_mask = 1ULL << RELAY_GPIO,
		.mode = GPIO_MODE_OUTPUT,
		.pull_down_en = 0,
		.pull_up_en = 0,
		.intr_type = GPIO_INTR_DISABLE,
	};
	gpio_config(&io_conf);
	gpio_set_level(RELAY_GPIO, 0);
}

static void publish_status(bool on)
{
	if (!s_mqtt_client) {
		return;
	}
	const char *payload = on ? "ON" : "OFF";
	esp_mqtt_client_publish(s_mqtt_client, MQTT_TOPIC_STATUS, payload, 0, 1, 0);
}

static void relay_task(void *arg)
{
	(void)arg;
	relay_cmd_t cmd;
	bool state_on = false;

	for (;;) {
		if (xQueueReceive(s_relay_queue, &cmd, portMAX_DELAY)) {
			state_on = (cmd == RELAY_CMD_ON);
			gpio_set_level(RELAY_GPIO, state_on);
			publish_status(state_on);
			ESP_LOGI(TAG, "Relay set to: %s", state_on ? "ON" : "OFF");
		}
	}
}

static void relay_post_cmd(relay_cmd_t cmd)
{
	if (s_relay_queue) {
		xQueueSend(s_relay_queue, &cmd, pdMS_TO_TICKS(100));
	}
}

static void mqtt_start(void);

static void mqtt_event_handler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
	(void)handler_args;
	(void)base;
	esp_mqtt_event_handle_t event = event_data;

	switch (event->event_id) {
	case MQTT_EVENT_CONNECTED:
		ESP_LOGI(TAG, "MQTT connected, subscribing");
		esp_mqtt_client_subscribe(event->client, MQTT_TOPIC_CMD, 1);
		break;
	case MQTT_EVENT_DATA: {
		/* Payload is not null-terminated; compare length explicitly */
		const char *payload = event->data;
		int len = event->data_len;
		ESP_LOGI(TAG, "MQTT cmd: %.*s", len, payload);

		if (len == 2 && strncmp(payload, "ON", 2) == 0) {
			relay_post_cmd(RELAY_CMD_ON);
		} else if (len == 3 && strncmp(payload, "OFF", 3) == 0) {
			relay_post_cmd(RELAY_CMD_OFF);
		} else {
			ESP_LOGW(TAG, "Unknown payload");
		}
		break;
	}
	case MQTT_EVENT_DISCONNECTED:
		ESP_LOGW(TAG, "MQTT disconnected");
		break;
	default:
		break;
	}
}

static void mqtt_start(void)
{
	if (s_mqtt_client) {
		return;
	}

	esp_mqtt_client_config_t mqtt_cfg = {
		.broker.address.uri = MQTT_URI,
		.session.keepalive = 60,
	};

	s_mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
	esp_mqtt_client_register_event(s_mqtt_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);
	ESP_ERROR_CHECK(esp_mqtt_client_start(s_mqtt_client));
}

static void mqtt_stop(void)
{
	if (!s_mqtt_client) {
		return;
	}
	esp_mqtt_client_stop(s_mqtt_client);
	esp_mqtt_client_destroy(s_mqtt_client);
	s_mqtt_client = NULL;
}

static void on_wifi_connected(void)
{
	ESP_LOGI(TAG, "WiFi connected, starting MQTT");
	mqtt_start();
}

static void on_wifi_disconnected(void)
{
	ESP_LOGW(TAG, "WiFi disconnected, stopping MQTT");
	mqtt_stop();
}

static void nvs_init(void)
{
	esp_err_t ret = nvs_flash_init();
	if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
		ESP_ERROR_CHECK(nvs_flash_erase());
		ESP_ERROR_CHECK(nvs_flash_init());
	}
}

void app_main(void)
{
	nvs_init();
	relay_gpio_init();

	s_relay_queue = xQueueCreate(4, sizeof(relay_cmd_t));
	xTaskCreate(relay_task, "relay_task", 2048, NULL, 5, NULL);

	/* Initialize ESP-Hosted transport (SDIO communication with ESP32-C6) */
	ESP_ERROR_CHECK(esp_hosted_init());

	/* Start WiFi Provisioning with callbacks for MQTT control */
	ESP_ERROR_CHECK(wifi_prov_start(on_wifi_connected, on_wifi_disconnected));

	ESP_LOGI(TAG, "Smart outlet started with WiFi Provisioning");
}
