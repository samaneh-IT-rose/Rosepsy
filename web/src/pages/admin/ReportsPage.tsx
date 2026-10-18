import { useCallback, useEffect, useState } from 'react';
import {
  getConsultantReport,
  getEventReport,
  getInvitedPersons,
  getReports,
  getReservationRequests,
  type ConsultantReportRow,
  type EventReportData,
  type ReportGroup,
} from '../../lib/admin';
import { faDate, faMoney } from '../../lib/jalali';

type ReportKey =
  | 'event-report'
  | 'undone-event-report'
  | 'event-group-report'
  | 'undone-event-group-report'
  | 'invitepersons'
  | 'admin-referrs-requests'
  | 'consultants'
  | undefined;

/** گزارشات — doc s.7: 3 groups, 10 cards; each card opens its backing report. */
export default function ReportsPage({ report }: { report?: string }) {
  const [groups, setGroups] = useState<ReportGroup[]>([]);
  const [active, setActive] = useState<ReportKey>(report as ReportKey);

  useEffect(() => {
    getReports().then((d) => setGroups(d.groups)).catch(() => {});
  }, []);
  useEffect(() => setActive(report as ReportKey), [report]);

  const CARD_TO_KEY: Record<string, ReportKey> = {
    '/event-report': 'event-report',
    '/undone-event-report': 'undone-event-report',
    '/event-group-report': 'event-group-report',
    '/undone-event-group-report': 'undone-event-group-report',
    '/invitepersons': 'invitepersons',
    '/admin-referrs-requests': 'admin-referrs-requests',
  };

  if (active) {
    return (
      <div className="admin-page">
        <button className="btn-ghost" onClick={() => setActive(undefined)}>
          ← بازگشت به گزارشات
        </button>
        {active === 'event-report' && <EventTable kind="individual" state="done" />}
        {active === 'undone-event-report' && <EventTable kind="individual" state="undone" />}
        {active === 'event-group-report' && <EventTable kind="group" state="done" />}
        {active === 'undone-event-group-report' && <EventTable kind="group" state="undone" />}
        {active === 'invitepersons' && <InvitedTable />}
        {active === 'admin-referrs-requests' && <RequestsTable />}
        {active === 'consultants' && <ConsultantTable />}
      </div>
    );
  }

  return (
    <div className="admin-page">
      <h2 className="admin-page-title">گزارشات</h2>
      {groups.map((g) => (
        <div key={g.title} className="admin-card">
          <div className="reports-section-header" style={{ borderRight: `4px solid ${GRAD(g.gradient)}` }}>
            <h3 className="admin-card-title">{g.title}</h3>
            <p className="admin-muted">{g.description}</p>
          </div>
          <div className="reports-grid">
            {g.cards.map((c) => (
              <button
                key={c.path}
                className="report-card"
                onClick={() => setActive(CARD_TO_KEY[c.path])}
              >
                <div className="report-card-content">
                  <h4>{c.title}</h4>
                  <p>{c.description}</p>
                </div>
                <span className="report-card-arrow">←</span>
              </button>
            ))}
          </div>
        </div>
      ))}
      <div className="admin-card">
        <div className="reports-section-header" style={{ borderRight: '4px solid #224abe' }}>
          <h3 className="admin-card-title">گزارش مشاوران و خدمات</h3>
          <p className="admin-muted">اطلاعات هویتی مشاور + ردیف‌های خدمت (سند §۸)</p>
        </div>
        <div className="reports-grid">
          <button className="report-card" onClick={() => setActive('consultants')}>
            <div className="report-card-content">
              <h4>گزارش مشاوران</h4>
              <p>فهرست مشاوران، تفکیک استانی/سرویس و خروجی CSV</p>
            </div>
            <span className="report-card-arrow">←</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function GRAD(g: string): string {
  const m = g.match(/#([0-9a-f]{6})/i);
  return m ? `#${m[1]}` : '#4e73df';
}

function EventTable({ kind, state }: { kind: 'individual' | 'group'; state: 'done' | 'undone' }) {
  const [data, setData] = useState<EventReportData | null>(null);
  useEffect(() => {
    getEventReport(kind, state, '&length=100').then(setData).catch(() => {});
  }, [kind, state]);
  if (!data) return <div className="admin-loading">در حال بارگذاری گزارش…</div>;
  return (
    <div className="admin-card">
      <h3 className="admin-card-title">
        {kind === 'group' ? 'جلسات گروهی' : 'جلسات فردی'} —{' '}
        {state === 'done' ? 'انجام‌شده' : 'ناتمام'} ({data.total.toLocaleString('fa-IR')} مورد)
      </h3>
      <table className="admin-table">
        <thead>
          <tr>
            <th>شناسه</th>
            <th>سرویس</th>
            <th>مشاور</th>
            <th>مرکز</th>
            <th>ارجاع</th>
            <th>وضعیت</th>
            <th>شروع</th>
            <th>پایان</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.length === 0 && (
            <tr>
              <td colSpan={8} className="admin-empty">
                موردی نیست
              </td>
            </tr>
          )}
          {data.rows.map((r) => (
            <tr key={r.code}>
              <td className="num">{r.code}</td>
              <td>{r.service ?? '—'}</td>
              <td>{r.consultant ?? '—'}</td>
              <td>{r.branch ?? '—'}</td>
              <td className="num">{r.referral_code ?? '—'}</td>
              <td>{r.status_fa}</td>
              <td className="num">{faDate(r.start_at, true)}</td>
              <td className="num">{faDate(r.end_at, true)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function InvitedTable() {
  const [data, setData] = useState<{ total: number; rows: Record<string, string | number | null>[] } | null>(null);
  const load = useCallback(() => {
    getInvitedPersons('?length=100').then(setData).catch(() => {});
  }, []);
  useEffect(load, [load]);
  if (!data) return <div className="admin-loading">در حال بارگذاری…</div>;
  return (
    <div className="admin-card">
      <h3 className="admin-card-title">
        کاربران معرفی‌شده ({data.total.toLocaleString('fa-IR')} مورد)
      </h3>
      <table className="admin-table">
        <thead>
          <tr>
            <th>کد</th>
            <th>نام</th>
            <th>موبایل</th>
            <th>استان</th>
            <th>نحوه ثبت‌نام</th>
            <th>تاریخ ثبت‌نام</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.length === 0 && (
            <tr>
              <td colSpan={6} className="admin-empty">
                موردی نیست
              </td>
            </tr>
          )}
          {data.rows.map((r, i) => (
            <tr key={String(r.id ?? i)}>
              <td className="num">{r.code ?? '—'}</td>
              <td>{r.full_name ?? '—'}</td>
              <td dir="ltr">{r.mobile ?? '—'}</td>
              <td>{r.province_fa ?? '—'}</td>
              <td>{r.registration_source ?? '—'}</td>
              <td className="num">{faDate(String(r.registered_at ?? ''))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RequestsTable() {
  const [data, setData] = useState<{ total: number; rows: Record<string, string | number | null>[] } | null>(null);
  useEffect(() => {
    getReservationRequests('?length=100').then(setData).catch(() => {});
  }, []);
  if (!data) return <div className="admin-loading">در حال بارگذاری…</div>;
  return (
    <div className="admin-card">
      <h3 className="admin-card-title">
        درخواست‌های رزرو کاربران ({data.total.toLocaleString('fa-IR')} مورد)
      </h3>
      <table className="admin-table">
        <thead>
          <tr>
            <th>شناسه</th>
            <th>کاربر</th>
            <th>موبایل</th>
            <th>سرویس</th>
            <th>مشاور</th>
            <th>مرکز</th>
            <th>ارجاع</th>
            <th>وضعیت</th>
            <th>شروع</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.length === 0 && (
            <tr>
              <td colSpan={9} className="admin-empty">
                موردی نیست
              </td>
            </tr>
          )}
          {data.rows.map((r, i) => (
            <tr key={String(r.code ?? i)}>
              <td className="num">{r.code ?? '—'}</td>
              <td>{r.user ?? '—'}</td>
              <td dir="ltr">{r.mobile ?? '—'}</td>
              <td>{r.service ?? '—'}</td>
              <td>{r.consultant ?? '—'}</td>
              <td>{r.branch ?? '—'}</td>
              <td className="num">{r.referral_code ?? '—'}</td>
              <td>{r.status_fa ?? '—'}</td>
              <td className="num">{faDate(String(r.start_at ?? ''), true)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConsultantTable() {
  const [groupBy, setGroupBy] = useState<'none' | 'province' | 'service'>('none');
  const [rows, setRows] = useState<ConsultantReportRow[] | null>(null);

  useEffect(() => {
    setRows(null);
    getConsultantReport(groupBy).then((d) => setRows(d.rows)).catch(() => setRows([]));
  }, [groupBy]);

  async function exportCsv() {
    const { getBlob } = await import('../../lib/admin');
    const blob = await getBlob(`/admin/reports/consultants?group_by=${groupBy}&format=csv`);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'moshavaran.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="admin-card">
      <div className="admin-filter-row">
        <h3 className="admin-card-title">گزارش مشاوران و خدمات</h3>
        <label className="admin-field">
          <span>تفکیک</span>
          <select
            className="admin-select"
            value={groupBy}
            onChange={(e) => setGroupBy(e.target.value as typeof groupBy)}
          >
            <option value="none">بدون تفکیک</option>
            <option value="province">تفکیک استانی</option>
            <option value="service">تفکیک سرویس</option>
          </select>
        </label>
        <button className="btn-ghost self-end" onClick={exportCsv}>
          خروجی CSV (moshavaran.csv)
        </button>
      </div>
      {!rows && <div className="admin-loading">در حال بارگذاری…</div>}
      {rows && rows.length === 0 && <div className="admin-empty">مشاوری ثبت نشده است</div>}
      {rows &&
        rows.map((c) => (
          <div key={c.row} className="admin-consultant">
            <div className="admin-consultant-head">
              <strong>
                {c.row}. {c.name}
              </strong>
              <span>کد ملی: {c.national_id ?? '—'}</span>
              <span dir="ltr">{c.mobile ?? '—'}</span>
              <span>مدرک: {c.degree ?? '—'}</span>
              <span>سطح: {c.level ?? '—'}</span>
              <span className="badge badge-green">جمع: {c.total_count} جلسه / {faMoney(c.total_amount)}</span>
            </div>
            {c.services.length > 0 && (
              <table className="admin-table slim">
                <thead>
                  <tr>
                    <th>استان</th>
                    <th>شهرستان</th>
                    <th>مرکز</th>
                    <th>سرویس</th>
                    <th>تعداد</th>
                    <th>مبلغ</th>
                  </tr>
                </thead>
                <tbody>
                  {c.services.map((s, i) => (
                    <tr key={i}>
                      <td>{s.province ?? '—'}</td>
                      <td>{s.city ?? '—'}</td>
                      <td>{s.branch ?? '—'}</td>
                      <td>{s.service ?? '—'}</td>
                      <td className="num">{s.count}</td>
                      <td className="num">{faMoney(s.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))}
    </div>
  );
}
