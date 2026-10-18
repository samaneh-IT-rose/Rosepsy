import { useCallback, useEffect, useState } from 'react';
import { getLogs, type LogRow } from '../../lib/admin';
import { faDate } from '../../lib/jalali';
import { Paged } from './ui';

/** گزارش فعالیت کاربران — doc s.3.1.2 item ۲۷ (from the immutable audit trail). */
export default function LogsPage() {
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const [length, setLength] = useState(10);
  const [data, setData] = useState<{ total: number; rows: LogRow[] } | null>(null);

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    params.set('start', String(page * (length === -1 ? 0 : length)));
    params.set('length', String(length));
    setData(await getLogs(`?${params.toString()}`));
  }, [q, page, length]);

  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  return (
    <div className="admin-page">
      <h2 className="admin-page-title">گزارش فعالیت کاربران</h2>
      <div className="admin-card">
        <div className="admin-filter-row">
          <label className="admin-field grow">
            <span>جستجو</span>
            <input
              value={q}
              onChange={(e) => {
                setPage(0);
                setQ(e.target.value);
              }}
              placeholder="اقدام، نتیجه، موبایل یا نام…"
            />
          </label>
        </div>
      </div>
      <div className="admin-card">
        <table className="admin-table">
          <thead>
            <tr>
              <th>زمان</th>
              <th>اقدام</th>
              <th>نتیجه</th>
              <th>کاربر</th>
              <th>موبایل</th>
              <th>موضوع</th>
              <th>شناسه درخواست</th>
              <th>IP</th>
            </tr>
          </thead>
          <tbody>
            {!data && (
              <tr>
                <td colSpan={8} className="admin-empty">
                  در حال بارگذاری…
                </td>
              </tr>
            )}
            {data && data.rows.length === 0 && (
              <tr>
                <td colSpan={8} className="admin-empty">
                  رویدادی ثبت نشده است
                </td>
              </tr>
            )}
            {data &&
              data.rows.map((l) => (
                <tr key={l.id}>
                  <td className="num">{faDate(l.created_at, true)}</td>
                  <td dir="ltr">{l.action}</td>
                  <td>
                    <span className={`badge ${l.outcome === 'ok' ? 'badge-green' : 'badge-red'}`}>
                      {l.outcome}
                    </span>
                  </td>
                  <td>{l.actor ?? '—'}</td>
                  <td dir="ltr">{l.actor_phone ?? '—'}</td>
                  <td dir="ltr">
                    {l.resource_type ?? '—'}
                    {l.resource_id ? ` / ${l.resource_id.slice(0, 8)}…` : ''}
                  </td>
                  <td dir="ltr" className="num">
                    {l.request_id ?? '—'}
                  </td>
                  <td dir="ltr">{l.ip ?? '—'}</td>
                </tr>
              ))}
          </tbody>
        </table>
        {data && (
          <Paged
            page={page}
            length={length}
            filtered={data.total}
            onPage={setPage}
            onLength={(l) => {
              setPage(0);
              setLength(l);
            }}
          />
        )}
      </div>
    </div>
  );
}
