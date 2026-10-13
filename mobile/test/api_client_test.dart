import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:roz_mobile/api_client.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });

  http.Client mockClient(int status, String body) => MockClient(
        (req) async => http.Response.bytes(utf8.encode(body), status),
      );

  test('verifyOtp stores token from envelope', () async {
    final client = ApiClient(
      baseUrl: 'http://test',
      httpClient: mockClient(
        200,
        '{"data":{"access_token":"tok123","token_type":"bearer",'
        '"is_new_user":true},"meta":{},"errors":null}',
      ),
    );
    final isNew = await client.verifyOtp('ch-1', '123456');
    expect(isNew, isTrue);
    expect(await client.token(), 'tok123');
  });

  test('error envelope raises ApiException', () async {
    final client = ApiClient(
      baseUrl: 'http://test',
      httpClient: mockClient(
        400,
        '{"data":null,"meta":{},"errors":['
        '{"code":"OTP_EXPIRED","message":"expired"}]}',
      ),
    );
    expect(
      () => client.verifyOtp('ch-1', '000000'),
      throwsA(isA<ApiException>()),
    );
  });
}
