# 🏠 Smart Power Outlet App - Flutter IoT Application

Ứng dụng di động iOS/Android chuyên nghiệp để điều khiển ổ cắm thông minh qua MQTT và cấu hình WiFi qua ESP32 Access Point.

## 🎯 Tính năng chính

### ✅ Điều khiển thiết bị
- Bật/tắt ổ cắm thông minh real-time qua MQTT
- Hiển thị trạng thái thiết bị từ ESP32
- Cập nhật trạng thái tự động khi có thay đổi

### 🌐 Kết nối MQTT  
- Kết nối tới server: `mqtt.toolhub.app:1883`
- Auto-reconnect khi mất kết nối
- QoS = 1 đảm bảo message delivery
- Client ID ngẫu nhiên tránh xung đột

### 📶 WiFi Provisioning
- Cấu hình WiFi cho ESP32 qua HTTP POST
- Kết nối tới ESP32 AP (192.168.4.1)
- Timeout handling an toàn

## 🏗️ Kiến trúc ứng dụng

### State Management
- **Riverpod** - Provider pattern hiện đại
- Stream-based reactive updates
- Clean separation of concerns

### Cấu trúc thư mục (Feature-first)
```
lib/
├── core/
│   ├── services/
│   │   ├── mqtt_service.dart          # MQTT client service
│   │   ├── provisioning_service.dart  # WiFi provisioning
│   │   ├── core_providers.dart        # Riverpod providers
│   │   ├── device_state.dart          # Device state model
│   │   └── connection_status.dart     # Connection status enum
│   └── theme/
│       ├── app_theme.dart             # Material 3 theme
│       └── app_colors.dart            # Color constants
├── features/
│   └── device_control/
│       └── presentation/
│           └── dashboard_screen.dart  # Main UI screen
├── app.dart                            # App widget
└── main.dart                           # Entry point
```

## 📦 Dependencies

```yaml
dependencies:
  flutter_riverpod: ^2.6.1    # State management
  mqtt_client: ^10.3.0        # MQTT protocol
  dio: ^5.7.0                 # HTTP client
  uuid: ^4.5.1                # UUID generation
  logger: ^2.5.0              # Logging utility
```

## 🚀 Hướng dẫn sử dụng

### 1. Cài đặt dependencies
```bash
cd smart_power_outlet_app
flutter pub get
```

### 2. Chạy ứng dụng
```bash
flutter run
```

### 3. Kết nối với thiết bị

#### Bước 1: Cấu hình WiFi (Provisioning)
1. ESP32 khởi động ở chế độ Access Point
2. Kết nối điện thoại với WiFi của ESP32
3. Mở app, vào màn hình Provisioning
4. Nhập SSID và Password WiFi nhà
5. Gửi cấu hình đến ESP32

#### Bước 2: Điều khiển thiết bị
1. ESP32 tự động kết nối MQTT sau khi có WiFi
2. App tự động kết nối MQTT khi khởi động
3. Màn hình Dashboard hiển thị:
   - Trạng thái kết nối (Online/Offline/Reconnecting)
   - Trạng thái thiết bị (ON/OFF)
   - Nút điều khiển bật/tắt

## 🔌 MQTT Topics

| Topic | Loại | Mô tả |
|-------|------|-------|
| `home/socket/status` | Subscribe | Nhận trạng thái thiết bị (ON/OFF) |
| `home/socket/cmd` | Publish | Gửi lệnh điều khiển (ON/OFF) |

## 🎨 UI/UX

- **Material Design 3** - Thiết kế hiện đại
- **Reactive UI** - Cập nhật real-time từ MQTT stream
- **Connection Indicator** - Hiển thị trạng thái kết nối
- **Responsive** - Tương thích iOS & Android

## 🔧 Cấu hình ESP32

ESP32 cần được lập trình với:
- MQTT Client (kết nối tới mqtt.toolhub.app:1883)
- Web Server ở chế độ AP (IP: 192.168.4.1)
- Endpoint POST `/` nhận `ssid` và `pass`

## 📱 Build for Production

### Android
```bash
flutter build apk --release
```

### iOS
```bash
flutter build ios --release
```

## 🐛 Troubleshooting

### MQTT không kết nối
- Kiểm tra kết nối internet
- Verify server: `mqtt.toolhub.app:1883` available
- Check firewall/network restrictions

### Provisioning thất bại
- Đảm bảo điện thoại đã kết nối ESP32 AP
- Kiểm tra ESP32 Web Server đang chạy
- Timeout có thể do kết nối WiFi chưa ổn định

## 📄 License

MIT License - Free for personal and commercial use

---

**Phát triển bởi:** Flutter IoT Smart Home Team  
**Version:** 1.0.0  
**Last Updated:** 2026
