import 'package:flutter/material.dart';

import '../api_client.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key, required this.client});

  final ApiClient client;

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  late Future<List<dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<dynamic>> _load() async {
    final items = await widget.client.notifications();
    for (final n in items) {
      if ((n as Map)['read'] == false) {
        await widget.client.markRead(n['id'] as String);
      }
    }
    return items;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<dynamic>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snap.hasError) {
          return Center(child: Text('خطا: ${snap.error}'));
        }
        final items = snap.data ?? [];
        if (items.isEmpty) {
          return const Center(child: Text('اعلانی ندارید'));
        }
        return ListView.builder(
          itemCount: items.length,
          itemBuilder: (context, i) {
            final n = items[i] as Map<String, dynamic>;
            final read = n['read'] == true;
            return ListTile(
              leading: Icon(
                read ? Icons.notifications_none : Icons.notifications_active,
              ),
              title: Text(n['title'] ?? ''),
              subtitle: Text(n['body'] ?? ''),
            );
          },
        );
      },
    );
  }
}