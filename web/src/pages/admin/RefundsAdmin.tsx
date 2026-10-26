import { useCallback, useEffect, useState } from 'react';
import { getRefunds, refundAction, type RefundRow } from '../../lib/admin';
import { faDate, faMoney } from '../../lib/jalali';

const STATUS_FA: Record<string, { label: string; color: string }> = {
  submitted: { label: 'ثبت‌شده', color: '#92400e' },
  reviewing: { label: 'در بررسی', color: '#1d4ed8' },
  approved: { label: 'تأییدشده', color: '#166534' },
  executed: { label: 'اجرا‌شده', color: '#166534' },
  rejected: { label: 'ردشده', color: '#b91c1c' },
};

/** استرداد وجه — پنل مالی B20: چرخه کامل submitted→reviewing→approved→executed|rejected. */
export default function RefundsAdmin() {
  const [rows, setRows] = useState<RefundRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('all');

  const load = useCallback(async () => {
    setErr(null);
    try {
      setRows(await getRefunds());
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function act(r: RefundRow, action: 'review' | 'approve' | 'reject' | 'execute') {
    const note =
      action === 'reject' || action === 'approve'
        ? window.prompt(action === 'reject' ? 'دلیل رد درخواست:' : 'یادداشت تأیید (اختیاری):') ?? ''
        : '';
    if (action === 'reject' && !note.trim()) return; // rejection requires a documented reason
    setBusyId(r.id + action);
    setErr(null);
    try {
      await refundAction(r.id, action, note || undefined);
      await load();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  const filtered = filter === 'all' ? rows : rows.filter((r) => r.status === filter);

  return (
    <div className="admin-page">
      <h2 className="admin-page-title">استرداد وجه (مالی)</h2>

      <div className="admin-card">
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
          {['all', 'submitted', 'reviewing', 'approved', 'executed', 'rejected'].map((s) => (
            <button
              key={s}
              className={`btn-ghost ${filter === s ? 'active' : ''}`}
              onClick={() => setFilter(s)}
              style={filter === s ? { background: '#fde7ef', color: '#9d174d' } : undefined}
            >
              {s === 'all' ? 'همه' : STATUS_FA[s]?.label ?? s}
            </button>
          ))}
        </div>

        {err && <div className="admin-error">{err}</div>}

        <table className="admin-table">
          <thead>
            <tr>
              <th>تاریخ</th>
              <th>سفارش</th>
              <th>مبلغ (ریال)</th>
              <th>دلیل</th>
              <th>وضعیت</th>
              <th>یادداشت تصمیم</th>
              <th>عملیات</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => {
              const st = STATUS_FA[r.status] ?? { label: r.status, color: '#374151' };
              return (
                <tr key={r.id}>
                  <td>{faDate(r.created_at, true)}</td>
                  <td style={{ direction: 'ltr', fontSize: 11 }}>{r.order_id.slice(0, 8)}…</td>
                  <td className="num">{faMoney(r.amount)}</td>
                  <td style={{ maxWidth: 200 }}>{r.reason}</td>
                  <td style={{ color: st.color, fontWeight: 600 }}>{st.label}</td>
                  <td style={{ maxWidth: 160 }}>{r.decision_note ?? '—'}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 4, justifyContent: 'center', flexWrap: 'wrap' }}>
                      {r.status === 'submitted' && (
                        <button className="btn-ghost" disabled={busyId === r.id + 'review'} onClick={() => act(r, 'review')}>
                          بررسی
                        </button>
                      )}
                      {(r.status === 'reviewing' || r.status === 'submitted') && (
                        <button className="btn-ghost" disabled={busyId === r.id + 'approve'} onClick={() => act(r, 'approve')}>
                          تأیید
                        </button>
                      )}
                      {r.status === 'approved' && (
                        <button className="btn-primary" disabled={busyId === r.id + 'execute'} onClick={() => act(r, 'execute')}>
                          اجرای واریز
                        </button>
                      )}
                      {['submitted', 'reviewing'].includes(r.status) && (
                        <button
                          className="btn-ghost"
                          disabled={busyId === r.id + 'reject'}
                          onClick={() => act(r, 'reject')}
                          style={{ color: '#b91c1c' }}
                        >
                          رد
                        </button>
                      )}
                      {['executed', 'rejected'].includes(r.status) && <span>—</span>}
                    </div>
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr><td colSpan={7} style={{ color: '#6b7280' }}>درخواستی در این وضعیت نیست.</td></tr>
            )}
          </tbody>
        </table>
        <p style={{ fontSize: 12, color: '#6b7280', marginTop: 10 }}>
          اجرای استرداد، وجه را به کیف پول متقاضی برمی‌گرداند؛ درخواست اجراشده تکرارپذیر نیست.
        </p>
      </div>
    </div>
  );
}
