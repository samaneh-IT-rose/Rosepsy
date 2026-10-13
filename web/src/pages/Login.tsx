import { useState } from 'react';
import { api, ApiException } from '../lib/api';
import { useAuth } from '../lib/auth';

export default function Login() {
  const { signIn } = useAuth();
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requestOtp = async () => {
    setBusy(true);
    setError(null);
    try {
      const d = await api.requestOtp(phone.trim());
      setChallengeId(d.challenge_id);
    } catch (e) {
      setError(e instanceof ApiException ? e.message : 'خطا');
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    setBusy(true);
    setError(null);
    try {
      if (!challengeId) return;
      const d = await api.verifyOtp(challengeId, code.trim());
      signIn(d.access_token);
    } catch (e) {
      setError(e instanceof ApiException ? e.message : 'خطا');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="container">
      <h1>ورود به کلینیک رز</h1>
      <input
        type="tel"
        placeholder="شماره موبایل (09xxxxxxxxx)"
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
      />
      {!challengeId && (
        <button onClick={requestOtp} disabled={busy}>
          دریافت کد
        </button>
      )}

      {challengeId && (
        <>
          <input
            type="text"
            placeholder="کد ۶ رقمی"
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          <button onClick={verify} disabled={busy}>
            تأیید و ورود
          </button>
        </>
      )}

      {error && <div className="error">{error}</div>}
    </div>
  );
}