idf_component_register(
    SRCS "main.c" "wifi_prov.c"
    INCLUDE_DIRS "."
    REQUIRES esp_hosted esp_wifi_remote esp_wifi esp_http_server mqtt nvs_flash driver
)
