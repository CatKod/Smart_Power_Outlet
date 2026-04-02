import 'package:flutter/material.dart';
import 'core/theme/app_theme.dart';
import 'features/device_control/presentation/dashboard_screen.dart';

/// Main Application Widget
class SmartPowerOutletApp extends StatelessWidget {
  const SmartPowerOutletApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Smart Power Outlet',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: ThemeMode.light,
      home: const DashboardScreen(),
    );
  }
}
