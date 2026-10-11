import 'package:flutter/material.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:provider/provider.dart';

import 'auth_state.dart';
import 'api_client.dart';
import 'screens/home_shell.dart';
import 'screens/login_screen.dart';

Future<void> main() async {
  await dotenv.load(fileName: '.env');
  final client = ApiClient(baseUrl: dotenv.get('API_BASE_URL'));
  final auth = AuthState(client);
  await auth.restore();
  runApp(RozApp(auth: auth));
}

class RozApp extends StatelessWidget {
  const RozApp({super.key, required this.auth});

  final AuthState auth;

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider.value(
      value: auth,
      child: MaterialApp(
        title: 'کلینیک رز',
        theme: ThemeData(
          useMaterial3: true,
          colorSchemeSeed: const Color(0xFF94365E),
        ),
        home: auth.isSignedIn ? const HomeShell() : const LoginScreen(),
      ),
    );
  }
}