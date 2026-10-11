import 'package:flutter/material.dart';

import '../api_client.dart';

class AppointmentsScreen extends StatefulWidget {
  const AppointmentsScreen({super.key, required this.client});

  final ApiClient client;

  @override
  State<AppointmentsScreen> createState() => _AppointmentsScreenState();
}

class _AppointmentsScreenState extends State<AppointmentsScreen> {
  late Future<List<dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.client.myAppointments();
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
          return const Center(child: Text('هنوز نوبتی ندارید'));
        }
        return RefreshIndicator(
          onRefresh: () async =>
              setState(() => _future = widget.client.myAppointments()),
          child: ListView.builder(
            itemCount: items.length,
            itemBuilder: (context, i) {
              final a = items[i] as Map<String, dynamic>;
              return ListTile(
                leading: const Icon(Icons.event),
                title: Text(a['start_at'].toString().replaceFirst('T', ' ')),
                subtitle: Text('وضعیت: ${a['status']}'),
              );
            },
          ),
        );
      },
    );
  }
}