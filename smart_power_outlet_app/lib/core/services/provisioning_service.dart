import 'dart:async';
import 'package:dio/dio.dart';
import 'package:logger/logger.dart';

/// Service for WiFi provisioning via ESP32 Access Point
///
/// Communicates with ESP32's web server at 192.168.4.1 to configure WiFi credentials
class ProvisioningService {
  ProvisioningService()
      : _dio = Dio(
          BaseOptions(
            baseUrl: 'http://192.168.4.1',
            connectTimeout: const Duration(seconds: 5),
            receiveTimeout: const Duration(seconds: 5),
            sendTimeout: const Duration(seconds: 5),
            headers: {
              'Content-Type': 'application/x-www-form-urlencoded',
            },
          ),
        ),
        _logger = Logger(printer: PrettyPrinter());

  final Dio _dio;
  final Logger _logger;

  /// Send WiFi credentials to ESP32 device
  ///
  /// [ssid] - WiFi network name
  /// [password] - WiFi password
  ///
  /// Returns true if provisioning was successful
  /// Throws [DioException] on network errors
  /// Throws [TimeoutException] if request takes longer than 5 seconds
  Future<bool> provisionWiFi({
    required String ssid,
    required String password,
  }) async {
    // Bỏ qua phần cấu hình WiFi qua Access Point của ESP32 theo yêu cầu
    _logger.i('Bỏ qua thao tác cấu hình WiFi AP (giả lập thành công)...');
    await Future.delayed(const Duration(milliseconds: 500)); 
    return true;
  }

  /// Test connection to ESP32 access point
  ///
  /// Returns true if ESP32 is reachable
  Future<bool> testConnection() async {
    try {
      _logger.d('Testing connection to ESP32...');
      final response = await _dio.get(
        '/',
        options: Options(
          validateStatus: (status) => true, // Accept any status code
        ),
      );
      
      _logger.d('Connection test response: ${response.statusCode}');
      return response.statusCode != null;
    } on DioException catch (e) {
      _logger.w('Connection test failed: ${e.type}');
      return false;
    } catch (e) {
      _logger.w('Connection test error: $e');
      return false;
    }
  }

  /// Dispose resources
  void dispose() {
    _logger.i('Disposing provisioning service');
    _dio.close();
  }
}
