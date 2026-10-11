import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

class ApiException implements Exception {
  ApiException(this.code, this.message);

  final String code;
  final String message;

  @override
  String toString() => '[$code] $message';
}

class ApiClient {
  ApiClient({required this.baseUrl, http.Client? httpClient})
      : _http = httpClient ?? http.Client();

  final String baseUrl;
  final http.Client _http;
  final _storage = const FlutterSecureStorage();
  static const _tokenKey = 'auth_token';

  String? lastChallengeId;

  Future<String?> token() => _storage.read(key: _tokenKey);

  Future<void> saveToken(String t) => _storage.write(key: _tokenKey, value: t);

  Future<void> clearToken() => _storage.delete(key: _tokenKey);

  Map<String, String> _headers(String? token) => {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

  dynamic _unwrap(http.Response r) {
    final body = jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
    final errors = body['errors'] as List?;
    if (r.statusCode >= 400 || (errors != null && errors.isNotEmpty)) {
      if (errors != null && errors.isNotEmpty) {
        final e = errors.first as Map<String, dynamic>;
        throw ApiException(
          e['code'] as String? ?? 'ERROR',
          e['message'] as String? ?? 'خطا',
        );
      }
      throw ApiException('HTTP_${r.statusCode}', 'خطای شبکه');
    }
    return body['data'];
  }

  Future<void> requestOtp(String phone) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/auth/otp/request'),
      headers: _headers(null),
      body: jsonEncode({'phone': phone}),
    );
    final data = _unwrap(r) as Map<String, dynamic>;
    lastChallengeId = data['challenge_id'] as String;
  }

  Future<bool> verifyOtp(String challengeId, String code) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/auth/otp/verify'),
      headers: _headers(null),
      body: jsonEncode({'challenge_id': challengeId, 'code': code}),
    );
    final data = _unwrap(r) as Map<String, dynamic>;
    await saveToken(data['access_token'] as String);
    return data['is_new_user'] == true;
  }

  Future<void> logout() => clearToken();

  Future<bool> hasSession() async => (await token()) != null;

  Future<List<dynamic>> myAppointments() async {
    final t = await token();
    final r = await _http.get(
      Uri.parse('$baseUrl/appointments'),
      headers: _headers(t),
    );
    return _unwrap(r) as List;
  }

  Future<List<dynamic>> notifications() async {
    final t = await token();
    final r = await _http.get(
      Uri.parse('$baseUrl/notifications'),
      headers: _headers(t),
    );
    return _unwrap(r) as List;
  }

  Future<void> markRead(String id) async {
    final t = await token();
    final r = await _http.post(
      Uri.parse('$baseUrl/notifications/$id/read'),
      headers: _headers(t),
    );
    _unwrap(r);
  }
}