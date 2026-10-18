import { useState, type FormEvent } from 'react';
import type { CenterRow, UserProfile, UserRow } from '../../lib/admin';
import { faDate } from '../../lib/jalali';

export function Modal({
  title,
  onClose,
  children,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="admin-modal-backdrop" onClick={onClose}>
      <div
        className={`admin-modal ${wide ? 'wide' : ''}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="admin-modal-head">
          <h3>{title}</h3>
          <button className="btn-ghost" onClick={onClose}>
            بستن ✕
          </button>
        </div>
        <div className="admin-modal-body">{children}</div>
      </div>
    </div>
  );
}

export function Paged(
  props: {
    page: number;
    length: number;
    filtered: number;
    onPage: (p: number) => void;
    onLength: (l: number) => void;
  },
) {
  const { page, length, filtered, onPage, onLength } = props;
  const pageSize = length === -1 ? Math.max(filtered, 1) : length;
  const last = Math.max(1, Math.ceil(filtered / pageSize));
  const from = filtered === 0 ? 0 : page * pageSize + 1;
  const to = Math.min(filtered, (page + 1) * pageSize);
  return (
    <div className="admin-pager">
      <label>
        نمایش
        <select
          value={length}
          onChange={(e) => onLength(Number(e.target.value))}
          className="admin-select"
        >
          {[10, 25, 50, 100, -1].map((n) => (
            <option key={n} value={n}>
              {n === -1 ? 'همه' : n}
            </option>
          ))}
        </select>
        رکورد
      </label>
      <span>
        {from} تا {to} از {filtered.toLocaleString('fa-IR')}
      </span>
      <div style={{ display: 'flex', gap: 4 }}>
        <button className="btn-ghost" disabled={page === 0} onClick={() => onPage(0)}>
          «
        </button>
        <button className="btn-ghost" disabled={page === 0} onClick={() => onPage(page - 1)}>
          قبلی
        </button>
        <span className="admin-pager-num">
          {page + 1} / {last}
        </span>
        <button
          className="btn-ghost"
          disabled={page + 1 >= last}
          onClick={() => onPage(page + 1)}
        >
          بعدی
        </button>
        <button
          className="btn-ghost"
          disabled={page + 1 >= last}
          onClick={() => onPage(last - 1)}
        >
          »
        </button>
      </div>
    </div>
  );
}

export function UserEditForm({
  user,
  onSaved,
  onCancel,
  save,
}: {
  user: UserRow;
  onSaved: () => void;
  onCancel: () => void;
  save: (id: string, body: Record<string, unknown>) => Promise<unknown>;
}) {
  const [form, setForm] = useState<Record<string, string>>({
    first_name: '',
    last_name: '',
    father_name: '',
    education: '',
    address: '',
    email: '',
    postal_code: '',
    city: '',
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: FormEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: (e.target as HTMLInputElement).value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const body: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(form)) if (v.trim()) body[k] = v.trim();
      await save(user.id, body);
      onSaved();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const F = (label: string, key: string) => (
    <label className="admin-field">
      <span>{label}</span>
      <input value={form[key]} onChange={set(key)} />
    </label>
  );

  return (
    <form onSubmit={submit} className="admin-grid-2">
      {F('نام', 'first_name')}
      {F('نام خانوادگی', 'last_name')}
      {F('نام پدر', 'father_name')}
      {F('تحصیلات', 'education')}
      {F('شهر', 'city')}
      {F('کد پستی', 'postal_code')}
      {F('ایمیل', 'email')}
      {F('آدرس', 'address')}
      {err && <div className="admin-error">{err}</div>}
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn-primary" disabled={busy}>
          {busy ? 'در حال ذخیره…' : 'ذخیره'}
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel}>
          انصراف
        </button>
      </div>
    </form>
  );
}

export function PersonalInfoBlock({ personal }: { personal: UserProfile['personal'] }) {
  const rows: [string, string][] = [
    ['کد ملی', 'national_id'],
    ['نام پدر', 'father_name'],
    ['شماره موبایل', 'mobile'],
    ['مدرک تحصیلی', 'education'],
    ['استان', 'province'],
    ['شهر', 'city'],
    ['جنسیت', 'gender_fa'],
    ['وضعیت تأهل', 'marital_status_fa'],
    ['تاریخ تولد', 'birth_date'],
    ['سن', 'age'],
    ['آدرس', 'address'],
  ];
  return (
    <div className="admin-card">
      <h3 className="admin-card-title">اطلاعات شخصی کاربر</h3>
      <div className="admin-grid-2">
        {rows.map(([label, key]) => {
          const raw = personal[key];
          const value =
            key === 'birth_date' && raw ? faDate(String(raw)) : raw === null || raw === undefined || raw === '' ? '—' : String(raw);
          return (
            <div key={key} className="admin-kv">
              <span className="admin-kv-label">{label}</span>
              <span>{value}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function CenterDetailBlock({ center }: { center: CenterRow & { clinic_name: string | null } }) {
  return (
    <div className="admin-grid-2">
      {(
        [
          ['نام کلینیک', center.name],
          ['کلینیک مادر', center.clinic_name],
          ['گروه', center.group],
          ['استان', center.province],
          ['شهر', center.city],
          ['وضعیت', center.is_active ? 'فعال' : 'غیرفعال'],
          ['شناسه جزئیات', center.legacy_code],
          ['آدرس', center.address],
        ] as [string, string | number | null][]
      ).map(([label, v]) => (
        <div key={label} className="admin-kv">
          <span className="admin-kv-label">{label}</span>
          <span>{v ?? '—'}</span>
        </div>
      ))}
    </div>
  );
}
