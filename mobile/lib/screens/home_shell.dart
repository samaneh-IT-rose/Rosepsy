import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../auth_state.dart';
import 'appointments_screen.dart';
import 'login_screen.dart';
import 'notifications_screen.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _tab = 0;

  @override
  Widget build(BuildContext context) {
    final client = context.read<AuthState>().client;
    final screens = [
      AppointmentsScreen(client: client),
      NotificationsScreen(client: client),
    ];
    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        appBar: AppBar(
          title: Text(_tab == 0 ? 'نوبت‌های من' : 'اعلان‌ها'),
          actions: [
            IconButton(
              icon: const Icon(Icons.logout),
              onPressed: () async {
                await context.read<AuthState>().signOut();
                if (context.mounted) {
                  Navigator.of(context).pushReplacement(
                    MaterialPageRoute(builder: (_) => const LoginScreen()),
                  );
                }
              },
            ),
          ],
        ),
        body: screens[_tab],
        bottomNavigationBar: NavigationBar(
          selectedIndex: _tab,
          onDestinationSelected: (i) => setState(() => _tab = i),
          destinations: const [
            NavigationDestination(icon: Icon(Icons.event), label: 'نوبت‌ها'),
            NavigationDestination(
                icon: Icon(Icons.notifications), label: 'اعلان‌ها'),
          ],
        ),
      ),
    );
  }
}