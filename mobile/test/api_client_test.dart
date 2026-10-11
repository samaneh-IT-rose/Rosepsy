import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:roz_mobile/api_client.dart';

void main() {
  test('verifyOtp stores token from envelope', () async {
    final client = ApiClient(
      baseUrl: 'http://test',
      httpClient: MockClient((req) async => http.Response(
            '{"data":{"access_token":"tok123","token_type":"bearer",'
            '"is_new_user":true},"meta":{},"errors":null}',
            200,
          )),
    );
    final isNew = await client.verifyOtp('ch-1', '123456');
    expect(isNew, isTrue);
    expect(await client.token(), 'tok123');
  });

  test('error envelope raises ApiException with Persian message', () async {
    final client = ApiClient(
      baseUrl: 'http://test',
      httpClient: MockClient((req) async => http.Response(
            '{"data":null,"meta":{},"errors":['
            '{"code":"OTP_EXPIRED","message":"اعتبار کد به پایان رسیده است"}]}',
            400,
          )),
    );
    expect(
      () => client.verifyOtp('ch-1', '000000'),
      throwsA(isA<ApiException>()),
    );
  });
}
