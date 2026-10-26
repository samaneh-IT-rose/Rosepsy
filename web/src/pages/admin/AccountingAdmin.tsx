import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  advanceSettlement,
  createAccount,
  createJournalEntry,
  createSettlement,
  getAccounts,
  getJournalEntries,
  getSettlements,
  type AccountRow,
  type JournalRow,
  type SettlementRow,
} from '../../lib/admin';
import { faDate, faMoney } from '../../lib/jalali';

const KINDS: [string, string][] = [
  ['asset', 'دارایی'],
  ['liability', 'بدهی'],
  ['equity', 'حقوق صاحبان سهام'],
  ['revenue', 'درآمد'],
  ['expense', 'هزینه'],
];
const KIND_FA: Record<string, string> = Object.fromEntries(KINDS);
const ST_FA: Record<string, string> = { draft: 'پیش‌نویس', approved: 'تأییدشده', paid: 'پرداخت‌شده' };

type Tab = 'accounts' | 'journal' | 'settlements';

/** حسابداری و تسویه — پنل مالی B22: کدینگ، اسناد خودنویس متوازن و تسویه مشاوران. */
export default function AccountingAdmin() {
  const [tab, setTab] = useState<Tab>('accounts');
  const [accounts, setAccounts] = useState<AccountRow[]>([]);
  const [journal, setJournal] = useState<JournalRow[]>([]);
  const [settlements, setSettlements] = useState<SettlementRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // account form
  const [acc, setAcc] = useState({ code: '', name: '', kind: 'asset' });
  // journal form (two lines: debit + credit)
  const [jl, setJl] = useState({
    debit_account: '',
    credit_account: '',
    amount: '',
    description: '',
  });
  // settlement form
  const [st, setSt] = useState({ consultant_id: '', from: '', to: '', gross: '', share: '70' });

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [a, j, s] = await Promise.all([getAccounts(), getJournalEntries(), getSettlements()]);
      setAccounts(a);
      setJournal(j);
      setSettlements(s);
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function submitAccount(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    setOkMsg(null);
    try {
      await createAccount({ code: acc.code.trim(), name: acc.name.trim(), kind: acc.kind });
      setOkMsg(`حساب «${acc.name}» ایجاد شد.`);
      setAcc({ code: '', name: '', kind: 'asset' });
      await load();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function submitJournal(e: FormEvent) {
    e.preventDefault();
    const amount = Number(jl.amount.replace(/[^\d]/g, ''));
    if (!jl.debit_account || !jl.credit_account || !amount) {
      setErr('حساب بدهکار، بستانکار و مبلغ الزامی است');
      return;
    }
    if (jl.debit_account === jl.credit_account) {
      setErr('حساب بدهکار و بستانکار باید متفاوت باشند');
      return;
    }
    setBusy(true);
    setErr(null);
    setOkMsg(null);
    try {
      await createJournalEntry({
        description: jl.description || undefined,
        lines: [
          { account_id: jl.debit_account, debit: amount, credit: 0 },
          { account_id: jl.credit_account, debit: 0, credit: amount },
        ],
      });
      setOkMsg('سند حسابداری ثبت شد.');
      setJl({ debit_account: '', credit_account: '', amount: '', description: '' });
      await load();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function submitSettlement(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    setOkMsg(null);
    try {
      await createSettlement({
        consultant_id: st.consultant_id.trim(),
        period_from: new Date(st.from).toISOString(),
        period_to: new Date(st.to).toISOString(),
        gross_amount: Number(st.gross.replace(/[^\d]/g, '') || 0),
        share_percent: Number(st.share || 0),
      });
      setOkMsg('تسویه ثبت شد.');
      setSt({ consultant_id: '', from: '', to: '', gross: '', share: '70' });
      await load();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function advance(s: SettlementRow) {
    setErr(null);
    try {
      await advanceSettlement(s.id);
      await load();
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }

  return (
    <div className="admin-page">
      <h2 className="admin-page-title">حسابداری و تسویه (مالی)</h2>

      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        {(
          [
            ['accounts', 'کدینگ حساب‌ها'],
            ['journal', 'اسناد حسابداری'],
            ['settlements', 'تسویه مشاوران'],
          ] as [Tab, string][]
        ).map(([k, label]) => (
          <button
            key={k}
            className={`btn-ghost ${tab === k ? 'active' : ''}`}
            onClick={() => setTab(k)}
            style={tab === k ? { background: '#fde7ef', color: '#9d174d' } : undefined}
          >
            {label}
          </button>
        ))}
      </div>

      {err && <div className="admin-error" style={{ marginBottom: 8 }}>{err}</div>}
      {okMsg && <div style={{ color: '#166534', marginBottom: 8 }}>{okMsg}</div>}

      {tab === 'accounts' && (
        <>
          <div className="admin-card">
            <h3 className="admin-card-title">افزودن حساب</h3>
            <form onSubmit={submitAccount} className="admin-grid-2">
              <label className="admin-field">
                <span>کد حساب *</span>
                <input value={acc.code} onChange={(e) => setAcc({ ...acc, code: e.target.value })} required />
              </label>
              <label className="admin-field">
                <span>نام حساب *</span>
                <input value={acc.name} onChange={(e) => setAcc({ ...acc, name: e.target.value })} required />
              </label>
              <label className="admin-field">
                <span>ماهیت</span>
                <select value={acc.kind} onChange={(e) => setAcc({ ...acc, kind: e.target.value })} className="admin-select">
                  {KINDS.map(([k, fa]) => (
                    <option key={k} value={k}>{fa}</option>
                  ))}
                </select>
              </label>
              <div style={{ display: 'flex', alignItems: 'flex-end' }}>
                <button className="btn-primary" disabled={busy}>{busy ? 'در حال ثبت…' : 'افزودن'}</button>
              </div>
            </form>
          </div>
          <div className="admin-card">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>کد</th>
                  <th>نام</th>
                  <th>ماهیت</th>
                  <th>مانده (ریال)</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a) => (
                  <tr key={a.id}>
                    <td style={{ direction: 'ltr' }}>{a.code}</td>
                    <td>{a.name}</td>
                    <td>{KIND_FA[a.kind] ?? a.kind}</td>
                    <td className="num">{faMoney(a.balance)}</td>
                  </tr>
                ))}
                {accounts.length === 0 && (
                  <tr><td colSpan={4} style={{ color: '#6b7280' }}>حسابی ثبت نشده است.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === 'journal' && (
        <>
          <div className="admin-card">
            <h3 className="admin-card-title">ثبت سند دوطرفه</h3>
            <form onSubmit={submitJournal} className="admin-grid-2">
              <label className="admin-field">
                <span>حساب بدهکار *</span>
                <select value={jl.debit_account} onChange={(e) => setJl({ ...jl, debit_account: e.target.value })} className="admin-select">
                  <option value="">انتخاب کنید…</option>
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>{a.code} — {a.name}</option>
                  ))}
                </select>
              </label>
              <label className="admin-field">
                <span>حساب بستانکار *</span>
                <select value={jl.credit_account} onChange={(e) => setJl({ ...jl, credit_account: e.target.value })} className="admin-select">
                  <option value="">انتخاب کنید…</option>
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>{a.code} — {a.name}</option>
                  ))}
                </select>
              </label>
              <label className="admin-field">
                <span>مبلغ (ریال) *</span>
                <input value={jl.amount} onChange={(e) => setJl({ ...jl, amount: e.target.value })} required />
              </label>
              <label className="admin-field">
                <span>شرح</span>
                <input value={jl.description} onChange={(e) => setJl({ ...jl, description: e.target.value })} />
              </label>
              <div style={{ display: 'flex', gap: 8, gridColumn: '1 / -1' }}>
                <button className="btn-primary" disabled={busy}>{busy ? 'در حال ثبت…' : 'ثبت سند'}</button>
              </div>
              <p style={{ gridColumn: '1 / -1', fontSize: 12, color: '#6b7280' }}>
                اسناد باید متوازن باشند (بدهکار = بستانکار)؛ سامانه اسناد نامتوازن را رد می‌کند.
              </p>
            </form>
          </div>
          <div className="admin-card">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>شماره سند</th>
                  <th>تاریخ</th>
                  <th>شرح</th>
                  <th>تفصیل آرتیکل‌ها</th>
                </tr>
              </thead>
              <tbody>
                {journal.map((j) => (
                  <tr key={j.id}>
                    <td style={{ direction: 'ltr' }}>{j.entry_no}</td>
                    <td>{faDate(j.posted_at, true)}</td>
                    <td>{j.description ?? j.source_type ?? '—'}</td>
                    <td style={{ textAlign: 'right' }}>
                      {j.lines.map((ln, i) => (
                        <div key={i} style={{ fontSize: 12 }}>
                          {ln.account_code ?? '؟'} {ln.account_name ?? ''} —{' '}
                          {ln.debit > 0 ? `بدهکار ${faMoney(ln.debit)}` : `بستانکار ${faMoney(ln.credit)}`}
                        </div>
                      ))}
                    </td>
                  </tr>
                ))}
                {journal.length === 0 && (
                  <tr><td colSpan={4} style={{ color: '#6b7280' }}>سندی ثبت نشده است.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === 'settlements' && (
        <>
          <div className="admin-card">
            <h3 className="admin-card-title">ثبت تسویه مشاور</h3>
            <form onSubmit={submitSettlement} className="admin-grid-2">
              <label className="admin-field">
                <span>شناسه مشاور *</span>
                <input value={st.consultant_id} onChange={(e) => setSt({ ...st, consultant_id: e.target.value })} placeholder="UUID مشاور" required />
              </label>
              <label className="admin-field">
                <span>سهم کلینیک (٪) — مکمل سهم مشاور</span>
                <input value={st.share} onChange={(e) => setSt({ ...st, share: e.target.value })} />
              </label>
              <label className="admin-field">
                <span>از تاریخ *</span>
                <input type="date" value={st.from} onChange={(e) => setSt({ ...st, from: e.target.value })} required />
              </label>
              <label className="admin-field">
                <span>تا تاریخ *</span>
                <input type="date" value={st.to} onChange={(e) => setSt({ ...st, to: e.target.value })} required />
              </label>
              <label className="admin-field">
                <span>مبلغ ناخالص (ریال) *</span>
                <input value={st.gross} onChange={(e) => setSt({ ...st, gross: e.target.value })} required />
              </label>
              <div style={{ display: 'flex', alignItems: 'flex-end' }}>
                <button className="btn-primary" disabled={busy}>{busy ? 'در حال ثبت…' : 'ثبت'}</button>
              </div>
            </form>
          </div>
          <div className="admin-card">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>مشاور</th>
                  <th>دوره</th>
                  <th>ناخالص</th>
                  <th>سهم ٪</th>
                  <th>خالص</th>
                  <th>وضعیت</th>
                  <th>عملیات</th>
                </tr>
              </thead>
              <tbody>
                {settlements.map((s) => (
                  <tr key={s.id}>
                    <td style={{ direction: 'ltr', fontSize: 11 }}>{s.consultant_id.slice(0, 8)}…</td>
                    <td>{faDate(s.period_from)} تا {faDate(s.period_to)}</td>
                    <td className="num">{faMoney(s.gross_amount)}</td>
                    <td className="num">{s.share_percent}٪</td>
                    <td className="num">{faMoney(s.net_amount)}</td>
                    <td>{ST_FA[s.status] ?? s.status}</td>
                    <td>
                      {s.status !== 'paid' && (
                        <button className="btn-ghost" onClick={() => advance(s)}>
                          {s.status === 'draft' ? 'تأیید' : 'ثبت پرداخت'}
                        </button>
                      )}
                      {s.status === 'paid' && s.paid_at && faDate(s.paid_at)}
                    </td>
                  </tr>
                ))}
                {settlements.length === 0 && (
                  <tr><td colSpan={7} style={{ color: '#6b7280' }}>تسویه‌ای ثبت نشده است.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
