import 'package:flutter/foundation.dart';

import 'api_client.dart';

class AuthState extends ChangeNotifier {
  AuthState(this.client);

  final ApiClient client;
  bool _isSignedIn = false;

  bool get isSignedIn => _isSignedIn;

  Future<void> restore() async =>
      _isSignedIn = await client.hasSession();

  Future<void> signIn(String challengeId, String code) async {
    await client.verifyOtp(challengeId, code);
    _isSignedIn = true;
    notifyListeners();
  }

  Future<void> signOut() async {
    await client.logout();
    _isSignedIn = false;
    notifyListeners();
  }
}