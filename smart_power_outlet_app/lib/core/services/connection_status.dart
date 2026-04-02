/// Represents the MQTT connection status
enum ConnectionStatus {
  disconnected('Offline'),
  connecting('Connecting'),
  connected('Online'),
  reconnecting('Reconnecting'),
  error('Error');

  const ConnectionStatus(this.label);
  final String label;
  
  bool get isConnected => this == ConnectionStatus.connected;
  bool get isDisconnected => this == ConnectionStatus.disconnected;
}
