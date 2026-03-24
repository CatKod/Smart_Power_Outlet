#include <stdio.h>
#include <string.h>
#include <stdbool.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "cJSON.h"

#define RELAY_GPIO              20
#define UART_PORT               UART_NUM_1
#define UART_TX_PIN             17
#define UART_RX_PIN             18
#define UART_BAUD               115200
#define UART_BUF_SIZE           1024
#define TX_QUEUE_LEN            8
#define TX_MSG_MAX              192

#define TOPIC_CMD               "home/socket/cmd"
#define TOPIC_STATUS            "home/socket/status"

static const char *TAG = "p4";

static QueueHandle_t tx_queue;
static bool relay_on = false;

static void relay_set(bool on)
{
	relay_on = on;
	gpio_set_level(RELAY_GPIO, on ? 1 : 0);
}

static void gpio_init_relay(void)
{
	gpio_config_t io = {
		.pin_bit_mask = 1ULL << RELAY_GPIO,
		.mode = GPIO_MODE_OUTPUT,
		.pull_up_en = GPIO_PULLUP_DISABLE,
		.pull_down_en = GPIO_PULLDOWN_ENABLE,
		.intr_type = GPIO_INTR_DISABLE,
	};
	gpio_config(&io);
	relay_set(false);
}

static void uart_init(void)
{
	uart_config_t cfg = {
		.baud_rate = UART_BAUD,
		.data_bits = UART_DATA_8_BITS,
		.parity = UART_PARITY_DISABLE,
		.stop_bits = UART_STOP_BITS_1,
		.flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
	};

	uart_driver_install(UART_PORT, UART_BUF_SIZE, UART_BUF_SIZE, 0, NULL, 0);
	uart_param_config(UART_PORT, &cfg);
	uart_set_pin(UART_PORT, UART_TX_PIN, UART_RX_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
}

static void enqueue_status_publish(void)
{
	char msg[TX_MSG_MAX];
	int n = snprintf(msg, sizeof(msg),
					 "{\"type\":\"pub\",\"topic\":\"%s\",\"payload\":\"%s\"}\n",
					 TOPIC_STATUS, relay_on ? "ON" : "OFF");
	if (n > 0 && n < (int)sizeof(msg)) {
		xQueueSend(tx_queue, msg, 0);
	}
}

static void handle_rx_line(const char *line)
{
	cJSON *root = cJSON_Parse(line);
	if (!root) {
		ESP_LOGW(TAG, "JSON parse fail: %s", line);
		return;
	}

	const cJSON *type = cJSON_GetObjectItem(root, "type");
	const cJSON *topic = cJSON_GetObjectItem(root, "topic");
	const cJSON *payload = cJSON_GetObjectItem(root, "payload");

	if (cJSON_IsString(type) && cJSON_IsString(topic) && cJSON_IsString(payload)) {
		if (strcmp(type->valuestring, "sub") == 0 && strcmp(topic->valuestring, TOPIC_CMD) == 0) {
			bool on = (strcasecmp(payload->valuestring, "ON") == 0);
			relay_set(on);
			enqueue_status_publish();
		}
	}

	cJSON_Delete(root);
}

static void uart_rx_task(void *arg)
{
	uint8_t buf[UART_BUF_SIZE];
	size_t offset = 0;
	while (1) {
		int len = uart_read_bytes(UART_PORT, buf + offset, sizeof(buf) - offset - 1, pdMS_TO_TICKS(100));
		if (len > 0) {
			offset += len;
			buf[offset] = '\0';

			// Process line-delimited JSON
			char *start = (char *)buf;
			char *newline;
			while ((newline = strchr(start, '\n')) != NULL) {
				*newline = '\0';
				if (strlen(start) > 0) {
					handle_rx_line(start);
				}
				start = newline + 1;
			}

			// Move remaining partial data to buffer start
			offset = strlen(start);
			memmove(buf, start, offset);
		}
	}
}

static void uart_tx_task(void *arg)
{
	char msg[TX_MSG_MAX];
	while (1) {
		if (xQueueReceive(tx_queue, msg, portMAX_DELAY) == pdTRUE) {
			int len = strlen(msg);
			uart_write_bytes(UART_PORT, msg, len);
			ESP_LOGI(TAG, "TX -> C6: %s", msg);
		}
	}
}

static void send_bootstrap(void)
{
	// Request C6 to join WiFi + connect MQTT and subscribe to cmd topic
	const char *ssid = "I2";
	const char *pwd = "abcd1232";
	const char *mqtt_host = "broker.hivemq.com";
	int mqtt_port = 1883;

	char msg[TX_MSG_MAX];
	int n = snprintf(msg, sizeof(msg),
					 "{\"type\":\"conn\",\"ssid\":\"%s\",\"pwd\":\"%s\",\"mqtt_host\":\"%s\",\"port\":%d,\"user\":\"\",\"pass\":\"\",\"sub\":\"%s\"}\n",
					 ssid, pwd, mqtt_host, mqtt_port, TOPIC_CMD);
	if (n > 0 && n < (int)sizeof(msg)) {
		xQueueSend(tx_queue, msg, 0);
	}
}

void app_main(void)
{
	nvs_flash_init();
	gpio_init_relay();
	uart_init();

	tx_queue = xQueueCreate(TX_QUEUE_LEN, TX_MSG_MAX);
	xTaskCreate(uart_rx_task, "uart_rx", 4096, NULL, 10, NULL);
	xTaskCreate(uart_tx_task, "uart_tx", 3072, NULL, 9, NULL);

	send_bootstrap();
}
