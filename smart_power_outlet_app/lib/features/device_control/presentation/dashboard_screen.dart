import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/services/core_providers.dart';
import '../../../../core/services/connection_status.dart';
import '../../../../core/services/device_state.dart';
import '../../../../core/theme/app_colors.dart';

/// Dashboard Screen - Main control interface for smart power outlet
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final connectionStatusAsync = ref.watch(connectionStatusProvider);
    final deviceStateAsync = ref.watch(deviceStateProvider);
    final deviceController = ref.read(deviceControllerProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Smart Power Outlet'),
        actions: [
          // Connection Status Indicator
          Padding(
            padding: const EdgeInsets.only(right: 16.0),
            child: Center(
              child: connectionStatusAsync.when(
                data: (status) => _ConnectionIndicator(status: status),
                loading: () => const _ConnectionIndicator(
                  status: ConnectionStatus.connecting,
                ),
                error: (_, _) => const _ConnectionIndicator(
                  status: ConnectionStatus.error,
                ),
              ),
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // Device Status Card
                Card(
                  elevation: 4,
                  child: Padding(
                    padding: const EdgeInsets.all(32.0),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        // Device Icon
                        deviceStateAsync.when(
                          data: (state) => _DeviceIcon(isOn: state.isOn),
                          loading: () => const _DeviceIcon(isOn: false),
                          error: (_, _) => const _DeviceIcon(isOn: false),
                        ),
                        const SizedBox(height: 24),
                        
                        // Device Status Text
                        deviceStateAsync.when(
                          data: (state) => Text(
                            state.isOn ? 'DEVICE ON' : 'DEVICE OFF',
                            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: state.isOn ? AppColors.deviceOn : AppColors.deviceOff,
                            ),
                          ),
                          loading: () => Text(
                            'LOADING...',
                            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: AppColors.deviceOff,
                            ),
                          ),
                          error: (_, _) => Text(
                            'ERROR',
                            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: AppColors.error,
                            ),
                          ),
                        ),
                        const SizedBox(height: 8),
                        
                        // Last Updated
                        deviceStateAsync.when(
                          data: (state) => Text(
                            'Updated: ${_formatTime(state.lastUpdated)}',
                            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: Colors.grey,
                            ),
                          ),
                          loading: () => const SizedBox.shrink(),
                          error: (_, _) => const SizedBox.shrink(),
                        ),
                        const SizedBox(height: 32),
                        
                        // Control Button
                        _ControlButton(
                          deviceStateAsync: deviceStateAsync,
                          onToggle: (value) async {
                            try {
                              await deviceController.toggleDevice(value);
                            } catch (e) {
                              if (context.mounted) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(
                                    content: Text('Error: $e'),
                                    backgroundColor: AppColors.error,
                                  ),
                                );
                              }
                            }
                          },
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 32),
                
                // Connection Info
                connectionStatusAsync.when(
                  data: (status) => _ConnectionInfo(status: status),
                  loading: () => const _ConnectionInfo(
                    status: ConnectionStatus.connecting,
                  ),
                  error: (_, _) => const _ConnectionInfo(
                    status: ConnectionStatus.error,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _formatTime(DateTime time) {
    return '${time.hour.toString().padLeft(2, '0')}:'
        '${time.minute.toString().padLeft(2, '0')}:'
        '${time.second.toString().padLeft(2, '0')}';
  }
}

/// Device Icon Widget
class _DeviceIcon extends StatelessWidget {
  const _DeviceIcon({required this.isOn});
  
  final bool isOn;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 120,
      height: 120,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: isOn ? AppColors.deviceOn.withValues(alpha: 0.2) : AppColors.deviceOff.withValues(alpha: 0.2),
        border: Border.all(
          color: isOn ? AppColors.deviceOn : AppColors.deviceOff,
          width: 4,
        ),
      ),
      child: Icon(
        Icons.power_settings_new,
        size: 64,
        color: isOn ? AppColors.deviceOn : AppColors.deviceOff,
      ),
    );
  }
}

/// Control Button Widget
class _ControlButton extends StatelessWidget {
  const _ControlButton({
    required this.deviceStateAsync,
    required this.onToggle,
  });
  
  final AsyncValue<DeviceState> deviceStateAsync;
  final Future<void> Function(bool) onToggle;

  @override
  Widget build(BuildContext context) {
    return deviceStateAsync.when(
      data: (state) => SizedBox(
        width: 200,
        height: 60,
        child: ElevatedButton.icon(
          onPressed: () => onToggle(!state.isOn),
          icon: Icon(
            state.isOn ? Icons.power_off : Icons.power,
            size: 28,
          ),
          label: Text(
            state.isOn ? 'TURN OFF' : 'TURN ON',
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
          style: ElevatedButton.styleFrom(
            backgroundColor: state.isOn ? AppColors.error : AppColors.deviceOn,
            foregroundColor: Colors.white,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(30),
            ),
          ),
        ),
      ),
      loading: () => const SizedBox(
        width: 200,
        height: 60,
        child: Center(
          child: CircularProgressIndicator(),
        ),
      ),
      error: (_, _) => SizedBox(
        width: 200,
        height: 60,
        child: ElevatedButton(
          onPressed: null,
          child: const Text('ERROR'),
        ),
      ),
    );
  }
}

/// Connection Status Indicator
class _ConnectionIndicator extends StatelessWidget {
  const _ConnectionIndicator({required this.status});
  
  final ConnectionStatus status;

  @override
  Widget build(BuildContext context) {
    Color color;
    switch (status) {
      case ConnectionStatus.connected:
        color = AppColors.connected;
        break;
      case ConnectionStatus.connecting:
      case ConnectionStatus.reconnecting:
        color = AppColors.connecting;
        break;
      case ConnectionStatus.disconnected:
      case ConnectionStatus.error:
        color = AppColors.disconnected;
        break;
    }

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 10,
          height: 10,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: color,
          ),
        ),
        const SizedBox(width: 8),
        Text(
          status.label,
          style: const TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}

/// Connection Information Widget
class _ConnectionInfo extends StatelessWidget {
  const _ConnectionInfo({required this.status});
  
  final ConnectionStatus status;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.grey.shade300),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            _getIconForStatus(status),
            size: 20,
            color: _getColorForStatus(status),
          ),
          const SizedBox(width: 8),
          Text(
            'MQTT: ${status.label}',
            style: TextStyle(
              fontSize: 14,
              color: _getColorForStatus(status),
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  IconData _getIconForStatus(ConnectionStatus status) {
    switch (status) {
      case ConnectionStatus.connected:
        return Icons.cloud_done;
      case ConnectionStatus.connecting:
      case ConnectionStatus.reconnecting:
        return Icons.cloud_sync;
      case ConnectionStatus.disconnected:
      case ConnectionStatus.error:
        return Icons.cloud_off;
    }
  }

  Color _getColorForStatus(ConnectionStatus status) {
    switch (status) {
      case ConnectionStatus.connected:
        return AppColors.connected;
      case ConnectionStatus.connecting:
      case ConnectionStatus.reconnecting:
        return AppColors.connecting;
      case ConnectionStatus.disconnected:
      case ConnectionStatus.error:
        return AppColors.disconnected;
    }
  }
}
