import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { createDiscount, getDiscounts, type DiscountRow } from '../../lib/admin';
import { faDate, faMoney } from '../../lib/jalali';

const KIND_FA: Record<string, string> = { percent: 'درصدی', fixed: 'مبلغ ثابت' };

/** کدهای تخفیف — پنل مالی B19: ایجاد و مشاهده کدها با سقف کل/کاربر. */
export default function DiscountsAdmin() {
  const [rows, setRows] = useState<DiscountRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    code: '',
    kind: 'fixed',
    value: '',
    min_order_amount: '',
    max_redemptions_total: '',
    max_redemptions_per_user: '',
  });

  const load = useCallback(async () => {
    setErr(null);
    try {
      setRows(await getDiscounts());
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const set = (k: string) => (e: FormEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: (e.target as HTMLInputElement).value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    setOkMsg(null);
    try {
      const body: Record<string, unknown> = {
        code: form.code.trim().toUpperCase(),
        kind: form.kind,
        value: Number(form.value.replace(/[^\d]/g, '')),
        min_order_amount: Number(form.min_order_amount.replace(/[^\d]/g, '') || 0),
      };
      if (form.max_redemptions_total) body.max_redemptions_total = Number(form.max_redemptions_total);
      if (form.max_redemptions_per_user) body.max_redemptions_per_user = Number(form.max_redemptions_per_user);
      await createDiscount(body);
      setOkMsg(`کد «${form.code.trim().toUpperCase()}» ایجاد شد.`);
      setForm({ code: '', kind: 'fixed', value: '', min_order_amount: '', max_redemptions_total: '', max_redemptions_per_user: '' });
      await load();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-page">
      <h2 className="admin-page-title">کدهای تخفیف (مالی)</h2>

      <div className="admin-card">
        <h3 className="admin-card-title">ایجاد کد تخفیف جدید</h3>
        <form onSubmit={submit} className="admin-grid-2">
          <label className="admin-field">
            <span>کد *</span>
            <input value={form.code} onChange={set('code')} placeholder="ROSE1400" required />
          </label>
          <label className="admin-field">
            <span>نوع</span>
            <select value={form.kind} onChange={set('kind')} className="admin-select">
              <option value="fixed">مبلغ ثابت (ریال)</option>
              <option value="percent">درصد</option>
            </select>
          </label>
          <label className="admin-field">
            <span>{form.kind === 'percent' ? 'درصد تخفیف *' : 'مبلغ تخفیف (ریال) *'}</span>
            <input value={form.value} onChange={set('value')} required />
          </label>
          <label className="admin-field">
            <span>حداقل مبلغ سفارش (ریال)</span>
            <input value={form.min_order_amount} onChange={set('min_order_amount')} placeholder="0" />
          </label>
          <label className="admin-field">
            <span>سقف کل مصرف</span>
            <input value={form.max_redemptions_total} onChange={set('max_redemptions_total')} placeholder="بدون سقف" />
          </label>
          <label className="admin-field">
            <span>سقف مصرف هر کاربر</span>
            <input value={form.max_redemptions_per_user} onChange={set('max_redemptions_per_user')} placeholder="بدون سقف" />
          </label>
          {err && <div className="admin-error" style={{ gridColumn: '1 / -1' }}>{err}</div>}
          {okMsg && <div style={{ gridColumn: '1 / -1', color: '#166534' }}>{okMsg}</div>}
          <div style={{ display: 'flex', gap: 8, gridColumn: '1 / -1' }}>
            <button className="btn-primary" disabled={busy}>{busy ? 'در حال ثبت…' : 'ایجاد کد'}</button>
          </div>
        </form>
      </div>

      <div className="admin-card">
        <h3 className="admin-card-title">کدهای ثبت‌شده</h3>
        {err && <div className="admin-error">{err}</div>}
        <table className="admin-table">
          <thead>
            <tr>
              <th>کد</th>
              <th>نوع</th>
              <th>مقدار</th>
              <th>حداقل سفارش</th>
              <th>سقف کل</th>
              <th>سقف کاربر</th>
              <th>اعتبار</th>
              <th>وضعیت</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.id}>
                <td style={{ direction: 'ltr' }}>{d.code}</td>
                <td>{KIND_FA[d.kind] ?? d.kind}</td>
                <td className="num">{d.kind === 'percent' ? `${d.value}٪` : faMoney(d.value)}</td>
                <td className="num">{faMoney(d.min_order_amount)}</td>
                <td className="num">{d.max_redemptions_total ?? '—'}</td>
                <td className="num">{d.max_redemptions_per_user ?? '—'}</td>
                <td>
                  {d.starts_at || d.ends_at
                    ? `${d.starts_at ? faDate(d.starts_at) : '…'} تا ${d.ends_at ? faDate(d.ends_at) : '…'}`
                    : '—'}
                </td>
                <td>{d.is_active ? 'فعال' : 'غیرفعال'}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={8} style={{ color: '#6b7280' }}>کدی ثبت نشده است.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
