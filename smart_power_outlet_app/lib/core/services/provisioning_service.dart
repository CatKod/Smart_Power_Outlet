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
    try {
      _logger.i('Starting WiFi provisioning for SSID: $ssid');

      // Prepare URL-encoded payload
      final data = {
        'ssid': ssid,
        'pass': password,
      };

      // Send POST request to ESP32
      final response = await _dio.post(
        '/',
        data: data,
        options: Options(
          contentType: Headers.formUrlEncodedContentType,
          validateStatus: (status) => status != null && status < 500,
        ),
      );

      _logger.i('Provisioning response: ${response.statusCode}');
      _logger.d('Response data: ${response.data}');

      // Consider 200-299 as success
      if (response.statusCode != null && response.statusCode! >= 200 && response.statusCode! < 300) {
        _logger.i('WiFi provisioning successful');
        return true;
      } else {
        _logger.w('Provisioning failed with status: ${response.statusCode}');
        return false;
      }
    } on DioException catch (e) {
      _logger.e('DioException during provisioning: ${e.type} - ${e.message}');
      
      if (e.type == DioExceptionType.connectionTimeout || 
          e.type == DioExceptionType.sendTimeout ||
          e.type == DioExceptionType.receiveTimeout) {
        _logger.e('Timeout: Make sure your phone is connected to ESP32 AP network');
        throw TimeoutException('Connection to ESP32 timed out. Please ensure you are connected to the device\'s WiFi network.');
      }
      
      if (e.type == DioExceptionType.connectionError) {
        _logger.e('Connection error: Cannot reach ESP32 at 192.168.4.1');
        throw Exception('Cannot connect to ESP32. Please verify you are connected to the device\'s WiFi network.');
      }
      
      rethrow;
    } catch (e) {
      _logger.e('Unexpected error during provisioning: $e');
      rethrow;
    }
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
