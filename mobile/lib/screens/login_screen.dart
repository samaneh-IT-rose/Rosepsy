import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api_client.dart';
import '../auth_state.dart';
import 'home_shell.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _phoneCtrl = TextEditingController();
  final _codeCtrl = TextEditingController();
  bool _otpSent = false;
  bool _busy = false;
  String? _error;

  Future<void> _requestOtp() async {
    final auth = context.read<AuthState>();
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await auth.client.requestOtp(_phoneCtrl.text.trim());
      setState(() => _otpSent = true);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      setState(() => _busy = false);
    }
  }

  Future<void> _verify() async {
    final auth = context.read<AuthState>();
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await auth.signIn(
        auth.client.lastChallengeId!,
        _codeCtrl.text.trim(),
      );
      if (mounted) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const HomeShell()),
        );
      }
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        appBar: AppBar(title: const Text('ورود به کلینیک رز')),
        body: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            children: [
              TextField(
                controller: _phoneCtrl,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(
                  labelText: 'شماره موبایل (09xxxxxxxxx)',
                ),
              ),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: _busy ? null : _requestOtp,
                child: const Text('دریافت کد'),
              ),
              if (_otpSent) ...[
                const SizedBox(height: 12),
                TextField(
                  controller: _codeCtrl,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: 'کد ۶ رقمی'),
                ),
                const SizedBox(height: 12),
                FilledButton(
                  onPressed: _busy ? null : _verify,
                  child: const Text('تأیید و ورود'),
                ),
              ],
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(
                    _error!,
                    style: const TextStyle(color: Colors.red),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}