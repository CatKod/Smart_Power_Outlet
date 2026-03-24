#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "nvs_flash.h"
#include "mqtt_client.h"
#include "cJSON.h"
#include "esp_log.h"

#define UART_PORT   UART_NUM_0
#define UART_BAUD   115200
#define BUF_SZ      1024

static const char *TAG = "c6";
static esp_mqtt_client_handle_t client;
static char topic_cmd[96] = "home/socket/cmd";

static void mqtt_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    esp_mqtt_event_handle_t e = data;
    if (id == MQTT_EVENT_DATA) {
        char payload[64] = {0};
        int len = e->data_len < (int)sizeof(payload) - 1 ? e->data_len : (int)sizeof(payload) - 1;
        memcpy(payload, e->data, len);

        cJSON *root = cJSON_CreateObject();
        cJSON_AddStringToObject(root, "type", "sub");
        cJSON_AddStringToObject(root, "topic", topic_cmd);
        cJSON_AddStringToObject(root, "payload", payload);
        char *json = cJSON_PrintUnformatted(root);
        if (json) {
            uart_write_bytes(UART_PORT, json, strlen(json));
            uart_write_bytes(UART_PORT, "\n", 1);
            cJSON_free(json);
        }
        cJSON_Delete(root);
    }
}

static void start_mqtt(const char *host, int port, const char *user, const char *pass)
{
    esp_mqtt_client_config_t cfg = {
        .broker.address.hostname = host,
        .broker.address.port = port,
        .credentials.username = user,
        .credentials.authentication.password = pass,
    };
    client = esp_mqtt_client_init(&cfg);
    esp_mqtt_client_register_event(client, ESP_EVENT_ANY_ID, mqtt_event, NULL);
    esp_mqtt_client_start(client);
    esp_mqtt_client_subscribe(client, topic_cmd, 0);
}

static void connect_wifi(const char *ssid, const char *pwd)
{
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    esp_wifi_init(&cfg);
    esp_wifi_set_mode(WIFI_MODE_STA);
    wifi_config_t sta = {0};
    strncpy((char *)sta.sta.ssid, ssid, sizeof(sta.sta.ssid));
    strncpy((char *)sta.sta.password, pwd, sizeof(sta.sta.password));
    esp_wifi_set_config(WIFI_IF_STA, &sta);
    esp_wifi_start();
    esp_wifi_connect();
}

static void uart_rx_task(void *arg)
{
    uint8_t buf[BUF_SZ];
    size_t off = 0;
    char ssid[33] = {0}, pwd[65] = {0}, host[64] = "broker.hivemq.com";
    int port = 1883; char user[64] = {0}, pass[64] = {0};

    while (1) {
        int n = uart_read_bytes(UART_PORT, buf + off, sizeof(buf) - off - 1, pdMS_TO_TICKS(100));
        if (n > 0) {
            off += n;
            buf[off] = 0;
            char *start = (char *)buf;
            char *nl;
            while ((nl = strchr(start, '\n'))) {
                *nl = 0;
                if (strlen(start)) {
                    cJSON *r = cJSON_Parse(start);
                    if (r) {
                        cJSON *j;
                        if ((j = cJSON_GetObjectItem(r, "type")) && cJSON_IsString(j) && strcmp(j->valuestring, "conn") == 0) {
                            if ((j = cJSON_GetObjectItem(r, "ssid"))) strncpy(ssid, j->valuestring, sizeof(ssid) - 1);
                            if ((j = cJSON_GetObjectItem(r, "pwd"))) strncpy(pwd, j->valuestring, sizeof(pwd) - 1);
                            if ((j = cJSON_GetObjectItem(r, "mqtt_host"))) strncpy(host, j->valuestring, sizeof(host) - 1);
                            if ((j = cJSON_GetObjectItem(r, "port"))) port = j->valueint;
                            if ((j = cJSON_GetObjectItem(r, "user"))) strncpy(user, j->valuestring, sizeof(user) - 1);
                            if ((j = cJSON_GetObjectItem(r, "pass"))) strncpy(pass, j->valuestring, sizeof(pass) - 1);
                            if ((j = cJSON_GetObjectItem(r, "sub"))) strncpy(topic_cmd, j->valuestring, sizeof(topic_cmd) - 1);
                            connect_wifi(ssid, pwd);
                            start_mqtt(host, port, user, pass);
                        }
                        cJSON_Delete(r);
                    }
                }
                start = nl + 1;
            }
            off = strlen(start);
            memmove(buf, start, off);
        }
    }
}

void app_main(void)
{
    nvs_flash_init();
    esp_event_loop_create_default();

    uart_config_t cfg = {
        .baud_rate = UART_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
    };
    uart_driver_install(UART_PORT, BUF_SZ, BUF_SZ, 0, NULL, 0);
    uart_param_config(UART_PORT, &cfg);

    xTaskCreate(uart_rx_task, "uart_rx", 4096, NULL, 10, NULL);
}
