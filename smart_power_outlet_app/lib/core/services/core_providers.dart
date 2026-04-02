import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../mqtt_sever_config.dart';
import '../services/mqtt_service.dart';
import '../services/provisioning_service.dart';
import '../services/connection_status.dart';
import '../services/device_state.dart';

/// Provider for MQTT Service (Singleton)
final mqttServiceProvider = Provider<MqttService>((ref) {
  final service = MqttService(
    broker: 'mqtt.toolhub.app',
    port: 1883,
    username: mqttUsername,
    password: mqttPassword,
  );
  
  // Auto-connect when app starts
  service.connect();
  
  // Dispose when provider is destroyed
  ref.onDispose(() {
    service.dispose();
  });
  
  return service;
});

/// Provider for Provisioning Service (Singleton)
final provisioningServiceProvider = Provider<ProvisioningService>((ref) {
  final service = ProvisioningService();
  
  ref.onDispose(() {
    service.dispose();
  });
  
  return service;
});

/// Stream Provider for MQTT Connection Status
final connectionStatusProvider = StreamProvider<ConnectionStatus>((ref) {
  final mqttService = ref.watch(mqttServiceProvider);
  return mqttService.connectionStatusStream;
});

/// Stream Provider for Device State
final deviceStateProvider = StreamProvider<DeviceState>((ref) {
  final mqttService = ref.watch(mqttServiceProvider);
  return mqttService.deviceStateStream;
});

/// Provider for Device Control Logic
final deviceControllerProvider = Provider((ref) {
  return DeviceController(ref);
});

/// Device Controller for handling device operations
class DeviceController {
  DeviceController(this._ref);
  
  final Ref _ref;
  
  /// Toggle device state (ON/OFF)
  Future<void> toggleDevice(bool turnOn) async {
    final mqttService = _ref.read(mqttServiceProvider);
    await mqttService.publishCommand(turnOn);
  }
  
  /// Get current connection status
  ConnectionStatus getConnectionStatus() {
    final mqttService = _ref.read(mqttServiceProvider);
    return mqttService.connectionStatus;
  }
  
  /// Get current device state
  DeviceState? getDeviceState() {
    final mqttService = _ref.read(mqttServiceProvider);
    return mqttService.deviceState;
  }
}
