import 'package:flutter/foundation.dart';

/// Represents the state of the smart power outlet device
@immutable
class DeviceState {
  final bool isOn;
  final DateTime lastUpdated;
  
  const DeviceState({
    required this.isOn,
    required this.lastUpdated,
  });
  
  factory DeviceState.initial() {
    return DeviceState(
      isOn: false,
      lastUpdated: DateTime.now(),
    );
  }
  
  DeviceState copyWith({
    bool? isOn,
    DateTime? lastUpdated,
  }) {
    return DeviceState(
      isOn: isOn ?? this.isOn,
      lastUpdated: lastUpdated ?? this.lastUpdated,
    );
  }
  
  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is DeviceState &&
        other.isOn == isOn &&
        other.lastUpdated == lastUpdated;
  }
  
  @override
  int get hashCode => Object.hash(isOn, lastUpdated);
  
  @override
  String toString() => 'DeviceState(isOn: $isOn, lastUpdated: $lastUpdated)';
}
