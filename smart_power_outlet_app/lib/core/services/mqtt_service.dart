import 'dart:async';
import 'dart:io';
import 'package:mqtt_client/mqtt_client.dart';
import 'package:mqtt_client/mqtt_server_client.dart';
import 'package:uuid/uuid.dart';
import 'package:logger/logger.dart';

import 'connection_status.dart';
import 'device_state.dart';

/// Service for managing MQTT connection and communication with smart power outlet
/// 
/// Features:
/// - Auto-reconnect on connection loss
/// - Random client ID to avoid conflicts
/// - QoS 1 for reliable message delivery
/// - Stream-based state updates
class MqttService {
  MqttService({
    required String broker,
    required int port,
    String? clientId,
  })  : _broker = broker,
        _port = port,
        _clientId = clientId ?? 'flutter_${const Uuid().v4().substring(0, 8)}',
        _logger = Logger(printer: PrettyPrinter());

  final String _broker;
  final int _port;
  final String _clientId;
  final Logger _logger;

  MqttServerClient? _client;
  
  // Stream controllers for reactive state management
  final _connectionStatusController = StreamController<ConnectionStatus>.broadcast();
  final _deviceStateController = StreamController<DeviceState>.broadcast();
  
  // Current state tracking
  ConnectionStatus _currentStatus = ConnectionStatus.disconnected;
  DeviceState? _currentDeviceState;
  
  // Getters for streams
  Stream<ConnectionStatus> get connectionStatusStream => _connectionStatusController.stream;
  Stream<DeviceState> get deviceStateStream => _deviceStateController.stream;
  ConnectionStatus get connectionStatus => _currentStatus;
  DeviceState? get deviceState => _currentDeviceState;
  
  /// Initialize and connect to MQTT broker
  Future<void> connect() async {
    try {
      _updateConnectionStatus(ConnectionStatus.connecting);
      _logger.i('Connecting to MQTT broker: $_broker:$_port with client ID: $_clientId');

      _client = MqttServerClient.withPort(_broker, _clientId, _port);
      
      // Configure client
      _client!.logging(on: false);
      _client!.keepAlivePeriod = 60;
      _client!.autoReconnect = true;
      _client!.onConnected = _onConnected;
      _client!.onDisconnected = _onDisconnected;
      _client!.onSubscribed = _onSubscribed;
      _client!.onAutoReconnect = _onAutoReconnect;
      _client!.onAutoReconnected = _onAutoReconnected;
      _client!.pongCallback = _onPong;

      // Connection message
      final connMessage = MqttConnectMessage()
          .withClientIdentifier(_clientId)
          .withWillQos(MqttQos.atLeastOnce)
          .startClean()
          .withWillRetain();
      
      _client!.connectionMessage = connMessage;

      // Attempt connection
      await _client!.connect();
      
      if (_client!.connectionStatus!.state == MqttConnectionState.connected) {
        _logger.i('MQTT client connected successfully');
        _subscribeToTopics();
        _setupMessageListener();
      } else {
        _logger.e('Connection failed - status: ${_client!.connectionStatus}');
        _updateConnectionStatus(ConnectionStatus.error);
        _client!.disconnect();
      }
    } on NoConnectionException catch (e) {
      _logger.e('NoConnectionException: $e');
      _updateConnectionStatus(ConnectionStatus.error);
      _client?.disconnect();
      rethrow;
    } on SocketException catch (e) {
      _logger.e('SocketException: $e');
      _updateConnectionStatus(ConnectionStatus.error);
      _client?.disconnect();
      rethrow;
    } catch (e) {
      _logger.e('Unexpected error during connection: $e');
      _updateConnectionStatus(ConnectionStatus.error);
      _client?.disconnect();
      rethrow;
    }
  }

  /// Subscribe to status topic to receive device state updates
  void _subscribeToTopics() {
    const String statusTopic = 'home/socket/status';
    _logger.i('Subscribing to topic: $statusTopic');
    _client!.subscribe(statusTopic, MqttQos.atLeastOnce);
  }

  /// Setup listener for incoming messages
  void _setupMessageListener() {
    _client!.updates!.listen((List<MqttReceivedMessage<MqttMessage>> messages) {
      final MqttPublishMessage message = messages[0].payload as MqttPublishMessage;
      final String payload = MqttPublishPayload.bytesToStringAsString(message.payload.message);
      final String topic = messages[0].topic;

      _logger.d('Received message: $payload from topic: $topic');

      if (topic == 'home/socket/status') {
        _handleStatusUpdate(payload);
      }
    });
  }

  /// Handle device status updates
  void _handleStatusUpdate(String payload) {
    final bool isOn = payload.trim().toUpperCase() == 'ON';
    final newState = DeviceState(
      isOn: isOn,
      lastUpdated: DateTime.now(),
    );
    
    _currentDeviceState = newState;
    _deviceStateController.add(newState);
    _logger.i('Device state updated: ${isOn ? "ON" : "OFF"}');
  }

  /// Publish command to control the device
  /// 
  /// [turnOn] - true to turn device ON, false to turn OFF
  Future<void> publishCommand(bool turnOn) async {
    if (_client == null || _client!.connectionStatus!.state != MqttConnectionState.connected) {
      _logger.w('Cannot publish: Client not connected');
      throw Exception('MQTT client not connected');
    }

    const String commandTopic = 'home/socket/cmd';
    final String command = turnOn ? 'ON' : 'OFF';
    
    final builder = MqttClientPayloadBuilder();
    builder.addString(command);
    
    _logger.i('Publishing command: $command to topic: $commandTopic');
    _client!.publishMessage(
      commandTopic,
      MqttQos.atLeastOnce,
      builder.payload!,
    );
  }

  /// Disconnect from MQTT broker
  void disconnect() {
    _logger.i('Disconnecting from MQTT broker');
    _client?.disconnect();
  }

  /// Dispose resources
  void dispose() {
    _logger.i('Disposing MQTT service');
    disconnect();
    _connectionStatusController.close();
    _deviceStateController.close();
  }

  // ============ MQTT Client Callbacks ============

  void _onConnected() {
    _logger.i('MQTT client connected');
    _updateConnectionStatus(ConnectionStatus.connected);
  }

  void _onDisconnected() {
    _logger.w('MQTT client disconnected');
    _updateConnectionStatus(ConnectionStatus.disconnected);
  }

  void _onSubscribed(String topic) {
    _logger.i('Subscription confirmed for topic: $topic');
  }

  void _onAutoReconnect() {
    _logger.i('Auto-reconnecting...');
    _updateConnectionStatus(ConnectionStatus.reconnecting);
  }

  void _onAutoReconnected() {
    _logger.i('Auto-reconnected successfully');
    _updateConnectionStatus(ConnectionStatus.connected);
    _subscribeToTopics(); // Re-subscribe after reconnection
  }

  void _onPong() {
    _logger.d('Ping response received');
  }

  // ============ Helper Methods ============

  void _updateConnectionStatus(ConnectionStatus status) {
    _currentStatus = status;
    _connectionStatusController.add(status);
  }
}
