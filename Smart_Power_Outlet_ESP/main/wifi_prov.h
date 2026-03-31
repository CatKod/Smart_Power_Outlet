#pragma once

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define CONFIG_WIFI_RMT_STATIC_RX_BUFFER_NUM 16
#define CONFIG_WIFI_RMT_DYNAMIC_RX_BUFFER_NUM 64
#define CONFIG_WIFI_RMT_TX_BUFFER_TYPE 0
#define CONFIG_WIFI_RMT_DYNAMIC_RX_MGMT_BUF 1

/* Launch provisioning: try STA with stored credentials, fail over to AP + captive portal when needed */
esp_err_t wifi_prov_start(void);

#ifdef __cplusplus
}
#endif
