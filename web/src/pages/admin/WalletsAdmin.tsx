import { useCallback, useEffect, useState } from 'react';
import {
  creditUserWallet,
  getUserWalletEntries,
  getWallets,
  type WalletEntryRow,
  type WalletRow,
} from '../../lib/admin';
import { faDate, faMoney } from '../../lib/jalali';
import { Modal, Paged } from './ui';

const PAGE_SIZE = 10;

/** کیف پول‌ها — پنل مالی B18: فهرست کیف پول، گردش حساب و شارژ دستی. */
export default function WalletsAdmin() {
  const [rows, setRows] = useState<WalletRow[]>([]);
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const [length, setLength] = useState(PAGE_SIZE);
  const [err, setErr] = useState<string | null>(null);
  const [detail, setDetail] = useState<{ user: WalletRow; entries: WalletEntryRow[] } | null>(null);
  const [credit, setCredit] = useState<WalletRow | null>(null);
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (query: string) => {
    setErr(null);
    try {
      setRows(await getWallets(query));
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }, []);

  useEffect(() => {
    load('');
  }, [load]);

  async function openDetail(w: WalletRow) {
    try {
      const entries = await getUserWalletEntries(w.user_id);
      setDetail({ user: w, entries });
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }

  async function submitCredit(e: React.FormEvent) {
    e.preventDefault();
    if (!credit) return;
    const amt = Number(amount.replace(/[^\d]/g, ''));
    if (!amt || amt <= 0) {
      setErr('مبلغ باید عددی مثبت باشد');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await creditUserWallet(
        credit.user_id,
        amt,
        note || undefined,
        `admin-credit-${credit.user_id}-${amt}-${Date.now()}`,
      );
      setCredit(null);
      setAmount('');
      setNote('');
      await load(q);
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const filtered = rows;
  const pageSize = length === -1 ? Math.max(filtered.length, 1) : length;
  const paged = filtered.slice(page * pageSize, (page + 1) * pageSize);

  return (
    <div className="admin-page">
      <h2 className="admin-page-title">کیف پول‌ها (مالی)</h2>

      <div className="admin-card">
        <div className="admin-toolbar" style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
          <input
            className="admin-input"
            placeholder="جست‌وجو بر اساس شناسه کاربر…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ flex: 1, minWidth: 220 }}
          />
          <button className="btn-ghost" onClick={() => { setPage(0); load(q); }}>
            جست‌وجو
          </button>
          <button className="btn-primary" onClick={() => setCredit({ id: '', user_id: q.trim(), currency: 'IRR', balance: 0, is_active: true })}>
            + شارژ دستی کیف پول
          </button>
        </div>

        {err && <div className="admin-error">{err}</div>}

        <table className="admin-table">
          <thead>
            <tr>
              <th>کاربر</th>
              <th>موجودی (ریال)</th>
              <th>ارز</th>
              <th>وضعیت</th>
              <th>عملیات</th>
            </tr>
          </thead>
          <tbody>
            {paged.map((w) => (
              <tr key={w.id || w.user_id}>
                <td style={{ direction: 'ltr', fontSize: 11 }}>{w.user_id.slice(0, 8)}…</td>
                <td className="num">{faMoney(w.balance)}</td>
                <td>{w.currency}</td>
                <td>{w.is_active ? 'فعال' : 'غیرفعال'}</td>
                <td>
                  <div style={{ display: 'flex', gap: 6, justifyContent: 'center' }}>
                    <button className="btn-ghost" onClick={() => openDetail(w)}>گردش</button>
                    <button
                      className="btn-ghost"
                      onClick={() => setCredit(w)}
                    >
                      شارژ
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {paged.length === 0 && (
              <tr>
                <td colSpan={5} style={{ color: '#6b7280' }}>کیف پولی ثبت نشده است.</td>
              </tr>
            )}
          </tbody>
        </table>
        <Paged
          page={page}
          length={length}
          filtered={filtered.length}
          onPage={setPage}
          onLength={(l) => { setLength(l); setPage(0); }}
        />
      </div>

      {detail && (
        <Modal title={`گردش کیف پول کاربر ${detail.user.user_id.slice(0, 8)}…`} onClose={() => setDetail(null)} wide>
          <div style={{ marginBottom: 8 }}>
            موجودی فعلی: <b>{faMoney(detail.user.balance)} ریال</b>
          </div>
          <table className="admin-table slim">
            <thead>
              <tr>
                <th>تاریخ</th>
                <th>نوع</th>
                <th>بدهکار</th>
                <th>بستانکار</th>
                <th>مانده پس از</th>
                <th>شرح</th>
              </tr>
            </thead>
            <tbody>
              {detail.entries.map((e) => (
                <tr key={e.id}>
                  <td>{faDate(e.created_at, true)}</td>
                  <td>{ENTRY_TYPE[e.entry_type] ?? e.entry_type}</td>
                  <td className="num">{e.direction === 'debit' ? faMoney(e.amount) : '—'}</td>
                  <td className="num">{e.direction === 'credit' ? faMoney(e.amount) : '—'}</td>
                  <td className="num">{faMoney(e.balance_after)}</td>
                  <td>{e.note ?? '—'}</td>
                </tr>
              ))}
              {detail.entries.length === 0 && (
                <tr><td colSpan={6} style={{ color: '#6b7280' }}>گردشی ثبت نشده است.</td></tr>
              )}
            </tbody>
          </table>
        </Modal>
      )}

      {credit && (
        <Modal title="شارژ دستی کیف پول" onClose={() => setCredit(null)}>
          <form onSubmit={submitCredit} className="admin-grid-2">
            <label className="admin-field" style={{ gridColumn: '1 / -1' }}>
              <span>شناسه کاربر</span>
              <input
                value={credit.user_id}
                onChange={(e) => setCredit({ ...credit, user_id: e.target.value })}
                placeholder="UUID کاربر"
                required
              />
            </label>
            <label className="admin-field">
              <span>مبلغ (ریال)</span>
              <input
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="مثلاً ۱٫۰۰۰٫۰۰۰ یا 1000000"
                required
              />
            </label>
            <label className="admin-field">
              <span>شرح</span>
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="بابت …" />
            </label>
            {err && <div className="admin-error" style={{ gridColumn: '1 / -1' }}>{err}</div>}
            <div style={{ display: 'flex', gap: 8, gridColumn: '1 / -1' }}>
              <button className="btn-primary" disabled={busy}>
                {busy ? 'در حال ثبت…' : 'ثبت شارژ'}
              </button>
              <button type="button" className="btn-ghost" onClick={() => setCredit(null)}>انصراف</button>
            </div>
            <p style={{ gridColumn: '1 / -1', fontSize: 12, color: '#6b7280' }}>
              عملیات با Idempotency-Key محافظت می‌شود؛ ثبت مجدد همان درخواست، شارژ تکراری نمی‌سازد.
            </p>
          </form>
        </Modal>
      )}
    </div>
  );
}

const ENTRY_TYPE: Record<string, string> = {
  topup: 'شارژ درگاهی',
  payment: 'پرداخت سفارش',
  refund: 'استرداد وجه',
  adjustment: 'تعدیل/شارژ دستی',
};
