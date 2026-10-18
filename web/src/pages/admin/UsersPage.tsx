import { useCallback, useEffect, useState } from 'react';
import {
  editUser,
  getCities,
  getProvinces,
  getUsers,
  switchSession,
  type UserRow,
} from '../../lib/admin';
import { faDate } from '../../lib/jalali';
import { navigate } from './router';
import { Modal, Paged, UserEditForm } from './ui';

/** Users management — doc s.4: regional filters, 11-column table, row-drop,
 * DataTables-style controls, openEdit + switchSession operations. */
export default function UsersPage() {
  const [provinces, setProvinces] = useState<{ code: number; name: string }[]>([]);
  const [cities, setCities] = useState<{ id: string; name: string }[]>([]);
  const [province, setProvince] = useState(0);
  const [city, setCity] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const [length, setLength] = useState(10);
  const [data, setData] = useState<{
    records_total: number;
    records_filtered: number;
    rows: UserRow[];
  } | null>(null);
  const [open, setOpen] = useState<string | null>(null); // row-drop user id
  const [editing, setEditing] = useState<UserRow | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getProvinces().then(setProvinces).catch(() => {});
  }, []);

  useEffect(() => {
    if (province > 0) getCities(province).then(setCities).catch(() => setCities([]));
    else setCities([]);
    setCity('');
  }, [province]);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const params = new URLSearchParams();
      if (province) params.set('province', String(province));
      if (city) params.set('city', city);
      if (q) params.set('q', q);
      params.set('start', String(page * (length === -1 ? 0 : length)));
      params.set('length', String(length));
      const d = await getUsers(`?${params.toString()}`);
      setData(d);
    } finally {
      setBusy(false);
    }
  }, [province, city, q, page, length]);

  useEffect(() => {
    load();
  }, [load]);

  async function doSwitch(u: UserRow) {
    setMsg(null);
    try {
      const t = await switchSession(u.id);
      localStorage.setItem('switched_token', t.access_token);
      setMsg(`توکن ورود به حساب ${u.full_name ?? u.mobile} ساخته شد (ممیزی شد).`);
    } catch (ex) {
      setMsg((ex as Error).message);
    }
  }

  const rows = data?.rows ?? [];

  return (
    <div className="admin-page">
      <h2 className="admin-page-title">مدیریت کاربران</h2>

      <div className="admin-card">
        <div className="admin-filter-row">
          <label className="admin-field">
            <span>استان</span>
            <select
              className="admin-select"
              value={province}
              onChange={(e) => {
                setPage(0);
                setProvince(Number(e.target.value));
              }}
            >
              <option value={0}>کل کشور</option>
              {provinces.filter((p) => p.code !== 0).map((p) => (
                <option key={p.code} value={p.code}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label className="admin-field">
            <span>شهرستان</span>
            <select
              className="admin-select"
              value={city}
              onChange={(e) => {
                setPage(0);
                setCity(e.target.value);
              }}
              disabled={province === 0}
            >
              <option value="">— همه —</option>
              {cities.map((c) => (
                <option key={c.id} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="admin-field grow">
            <span>جستجو</span>
            <input
              value={q}
              onChange={(e) => {
                setPage(0);
                setQ(e.target.value);
              }}
              placeholder="نام، نام کاربری، کد ملی یا موبایل…"
            />
          </label>
        </div>
      </div>

      <div className="admin-card">
        <table className="admin-table">
          <thead>
            <tr>
              <th>کد</th>
              <th>نام کاربری</th>
              <th>نام و نام خانوادگی</th>
              <th className="hide-m">نام پدر</th>
              <th>جنسیت</th>
              <th className="hide-m">شماره همراه</th>
              <th className="hide-m">استان</th>
              <th className="hide-m">تحصیلات</th>
              <th className="hide-m">تاریخ تولد</th>
              <th className="hide-m">تاریخ ثبت‌نام</th>
              <th className="hide-m">آخرین ورود</th>
              <th>عملیات</th>
            </tr>
          </thead>
          <tbody>
            {busy && (
              <tr>
                <td colSpan={12} className="admin-empty">
                  در حال پردازش…
                </td>
              </tr>
            )}
            {!busy && rows.length === 0 && (
              <tr>
                <td colSpan={12} className="admin-empty">
                  رکوردی یافت نشد
                </td>
              </tr>
            )}
            {!busy &&
              rows.map((u) => (
                <>
                  <tr key={u.id}>
                    <td className="num">{u.code ?? '—'}</td>
                    <td className="num">{u.username ?? '—'}</td>
                    <td>{u.full_name ?? '—'}</td>
                    <td className="hide-m">{u.father_name ?? '—'}</td>
                    <td>{u.gender_fa ?? '—'}</td>
                    <td className="hide-m" dir="ltr">
                      <a href={`tel:${u.mobile}`}>{u.mobile}</a>
                    </td>
                    <td className="hide-m">{u.province_fa ?? '—'}</td>
                    <td className="hide-m">{u.education ?? '—'}</td>
                    <td className="hide-m">{u.birth_date ? faDate(u.birth_date) : '—'}</td>
                    <td className="hide-m">{faDate(u.registered_at)}</td>
                    <td className="hide-m">
                      {u.last_login_at ? faDate(u.last_login_at, true) : 'ثبت نشده'}
                    </td>
                    <td>
                      <div className="admin-actions">
                        <button
                          className="btn-mini"
                          onClick={() => setOpen(open === u.id ? null : u.id)}
                        >
                          اطلاعات بیشتر
                        </button>
                        <button className="btn-mini" onClick={() => setEditing(u)}>
                          ویرایش
                        </button>
                        <button className="btn-mini warn" onClick={() => doSwitch(u)}>
                          ورود
                        </button>
                      </div>
                    </td>
                  </tr>
                  {open === u.id && (
                    <tr key={`${u.id}-drop`} className="row-drop">
                      <td colSpan={12}>
                        <div className="admin-drop">
                          {(
                            [
                              ['نام کاربری', u.details.username],
                              ['ایمیل', u.details.email],
                              ['آدرس', u.details.address],
                              ['کد پستی', u.details.postal_code],
                              ['نحوه ثبت‌نام', u.details.registration_source],
                            ] as [string, string | null][]
                          ).map(([k, v]) => (
                            <div key={k} className="admin-kv">
                              <span className="admin-kv-label">{k}</span>
                              <span>{v ?? 'ثبت نشده'}</span>
                            </div>
                          ))}
                          <button
                            className="btn-mini"
                            onClick={() => navigate('user-profile', { user: u.id })}
                          >
                            پرونده و خدمات کاربر →
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
          </tbody>
        </table>
        {data && (
          <Paged
            page={page}
            length={length}
            filtered={data.records_filtered}
            onPage={setPage}
            onLength={(l) => {
              setPage(0);
              setLength(l);
            }}
          />
        )}
        {msg && <div className="admin-note">{msg}</div>}
      </div>

      {editing && (
        <Modal title={`ویرایش کاربر — ${editing.full_name ?? editing.mobile}`} onClose={() => setEditing(null)}>
          <UserEditForm
            user={editing}
            save={editUser}
            onCancel={() => setEditing(null)}
            onSaved={() => {
              setEditing(null);
              setMsg('ذخیره شد و در گزارش فعالیت ثبت شد.');
              load();
            }}
          />
        </Modal>
      )}
    </div>
  );
}
