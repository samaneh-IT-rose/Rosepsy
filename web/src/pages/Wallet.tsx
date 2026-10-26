import { useCallback, useEffect, useState } from 'react';
import { api } from '../lib/api';

type Wallet = { id: string; balance: number; currency: string };
type Entry = {
  id: string;
  direction: 'credit' | 'debit';
  amount: number;
  balance_after: number;
  entry_type: string;
  note: string | null;
  created_at: string;
};

const TYPE_FA: Record<string, string> = {
  topup: 'شارژ',
  payment: 'پرداخت',
  refund: 'استرداد',
  adjustment: 'اصلاحیه',
};

const row: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  gap: 8,
  padding: '10px 12px',
  border: '1px solid #e5e7eb',
  borderRadius: 10,
  background: '#fff',
  textAlign: 'right',
  fontSize: 12,
};

export default function WalletPage() {
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [amount, setAmount] = useState('500000');
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setWallet(await api.request<Wallet>('/wallet'));
      const res = await api.request<Entry[]>('/wallet/entries');
      setEntries(res);
    } catch {
      setMsg('خطا در دریافت کیف پول');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const topup = async () => {
    setMsg(null);
    try {
      const order = await api.request<{ id: string }>('/wallet-topups', {
        method: 'POST',
        headers: { 'Idempotency-Key': `ui-${Date.now()}` },
        body: JSON.stringify({ amount: Number(amount) }),
      });
      const pay = await api.request<{ gateway_ref: string }>('/payments/start', {
        method: 'POST',
        body: JSON.stringify({ order_id: order.id }),
      });
      await api.request<{ order_status: string }>('/payments/callback', {
        method: 'POST',
        body: JSON.stringify({ gateway_ref: pay.gateway_ref, result: 'success' }),
      });
      setMsg('شارژ کیف پول با موفقیت انجام شد ✅');
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'خطا در شارژ');
    }
  };

  return (
    <div style={{ padding: 16, display: 'grid', gap: 14, textAlign: 'right' }}>
      <h2 style={{ margin: 0 }}>کیف پول</h2>
      <div
        style={{
          padding: '18px 20px',
          borderRadius: 14,
          background: 'linear-gradient(125deg,#5d294c,#913857)',
          color: '#fff',
        }}
      >
        <div style={{ fontSize: 12, opacity: 0.85 }}>مانده قابل استفاده</div>
        <div style={{ fontSize: 28, fontWeight: 'bold' }}>
          {(wallet?.balance ?? 0).toLocaleString('fa-IR')} {wallet?.currency ?? 'IRR'}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <input
          value={amount}
          onChange={(e) => setAmount(e.target.value.replace(/\D/g, ''))}
          inputMode="numeric"
          style={{
            padding: '8px 12px',
            borderRadius: 8,
            border: '1px solid #e5e7eb',
            flex: 1,
          }}
        />
        <button
          onClick={() => void topup()}
          style={{
            padding: '8px 18px',
            borderRadius: 8,
            border: '1px solid #94365e',
            background: '#94365e',
            color: '#fff',
            cursor: 'pointer',
          }}
        >
          شارژ از درگاه
        </button>
      </div>
      {msg && (
        <div style={{ background: '#eaf7f5', padding: '8px 12px', borderRadius: 8 }}>{msg}</div>
      )}

      <h3 style={{ margin: '4px 0 0' }}>گردش‌ها</h3>
      <div style={{ display: 'grid', gap: 6 }}>
        {entries.map((e) => (
          <div key={e.id} style={row}>
            <span>
              <strong style={{ color: e.direction === 'credit' ? '#1f7a44' : '#c53939' }}>
                {e.direction === 'credit' ? '+' : '−'}
                {e.amount.toLocaleString('fa-IR')}
              </strong>{' '}
              {TYPE_FA[e.entry_type] || e.entry_type}
            </span>
            <span style={{ color: '#607385' }}>
              مانده: {e.balance_after.toLocaleString('fa-IR')}
            </span>
          </div>
        ))}
        {entries.length === 0 && <p style={{ color: '#607385' }}>گردشی ثبت نشده است.</p>}
      </div>
    </div>
  );
}
