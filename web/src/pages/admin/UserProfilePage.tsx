import { useEffect, useState } from 'react';
import { getEventDetails, getUserProfile, type EventDetails, type UserProfile } from '../../lib/admin';
import { faDate, faMoney } from '../../lib/jalali';
import { Modal } from './ui';

const ACUTE_BADGE: Record<string, string> = {
  'خیر': 'badge-gray',
  'در انتظار': 'badge-amber',
  'بله': 'badge-red',
};

/** پرونده کاربر — doc s.5: personal info + 12-column services table + «بیشتر». */
export default function UserProfilePage({ userId }: { userId: string | null }) {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [detail, setDetail] = useState<EventDetails | null>(null);
  const [detailKind, setDetailKind] = useState<string>('0');

  useEffect(() => {
    if (!userId) return;
    setProfile(null);
    setErr(null);
    getUserProfile(userId)
      .then(setProfile)
      .catch((ex) => setErr((ex as Error).message));
  }, [userId]);

  async function openDetails(code: number, kind: string) {
    setDetailKind(kind);
    try {
      const d = await getEventDetails(code, kind);
      setDetail(d);
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }

  if (!userId) {
    return (
      <div className="admin-page">
        <h2 className="admin-page-title">پرونده کاربر</h2>
        <div className="admin-card" style={{ textAlign: 'center', padding: 40 }}>
          برای مشاهده پرونده، از صفحه «مدیریت کاربران» روی «پرونده و خدمات کاربر»
          کلیک کنید.
        </div>
      </div>
    );
  }

  if (err)
    return (
      <div className="admin-page">
        <div className="admin-error">{err}</div>
      </div>
    );

  if (!profile) return <div className="admin-loading">در حال بارگذاری پرونده…</div>;

  const rows = profile.services.rows;

  return (
    <div className="admin-page">
      <h2 className="admin-page-title">پرونده کاربر</h2>

      <PersonalBlock personal={profile.personal} />

      <div className="admin-card">
        <h3 className="admin-card-title">جدول خدمات کاربر</h3>
        <div style={{ overflowX: 'auto' }}>
          <table className="admin-table">
            <thead>
              <tr>
                <th>شناسه</th>
                <th>شناسه ارجاع</th>
                <th>سرویس</th>
                <th>قرارداد</th>
                <th>تعرفه کاربر</th>
                <th>کیس حاد</th>
                <th>مشاور</th>
                <th>مرکز</th>
                <th>وضعیت</th>
                <th>تاریخ شروع</th>
                <th>تاریخ پایان</th>
                <th>بیشتر</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={12} className="admin-empty">
                    خدمتی ثبت نشده است
                  </td>
                </tr>
              )}
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="num">{r.code}</td>
                  <td className="num">{r.referral_code ?? '—'}</td>
                  <td>{r.service ?? '—'}</td>
                  <td>{r.contract ?? '—'}</td>
                  <td className="num">{faMoney(r.user_tariff)}</td>
                  <td>
                    <span className={`badge ${ACUTE_BADGE[r.acute_fa ?? 'خیر'] ?? 'badge-gray'}`}>
                      {r.acute_fa ?? '—'}
                    </span>
                  </td>
                  <td>{r.consultant ?? '—'}</td>
                  <td>{r.branch ?? '—'}</td>
                  <td>{r.status_fa ?? '—'}</td>
                  <td className="num">{faDate(r.start_at, true)}</td>
                  <td className="num">{faDate(r.end_at, true)}</td>
                  <td>
                    <select
                      className="admin-select blue"
                      value="0"
                      onChange={(e) => {
                        if (e.target.value !== '0') {
                          openDetails(r.code, e.target.value);
                          e.target.value = '0';
                        }
                      }}
                    >
                      {(r.details_options ?? [{ value: '0', title: 'جزئیات' }]).map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.title}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {detail && (
        <Modal
          title="جزئیات"
          onClose={() => setDetail(null)}
        >
          <DetailBody detail={detail} kind={detailKind} />
        </Modal>
      )}
    </div>
  );
}

function DetailBody({ detail, kind }: { detail: EventDetails; kind: string }) {
  if (kind === 'REFF' && detail.referral) {
    const r = detail.referral;
    return (
      <div className="admin-grid-2">
        {(
          [
            ['شناسه ارجاع', r.code],
            ['قرارداد', r.contract],
            ['تعرفه کاربر', faMoney(Number(r.user_tariff ?? 0))],
            ['وضعیت', r.status_fa],
            ['منشأ (نحوه ثبت‌نام)', r.source],
            ['تاریخ ایجاد', faDate(String(r.created_at ?? ''), true)],
          ] as [string, string | number | null][]
        ).map(([k, v]) => (
          <div key={k} className="admin-kv">
            <span className="admin-kv-label">{k}</span>
            <span>{v ?? '—'}</span>
          </div>
        ))}
      </div>
    );
  }
  const e = detail.event;
  if (!e) return <p>اطلاعاتی برای این انتخاب نیست.</p>;
  return (
    <div className="admin-grid-2">
      {(
        [
          ['شناسه جلسه', e.code],
          ['سرویس', e.service],
          ['مشاور', e.consultant],
          ['مرکز', e.branch],
          ['وضعیت', e.status_fa],
          ['کیس حاد', e.acute_fa],
          ['شروع', faDate(String(e.start_at ?? ''), true)],
          ['پایان', faDate(String(e.end_at ?? ''), true)],
        ] as [string, string | number | null][]
      ).map(([k, v]) => (
        <div key={k} className="admin-kv">
          <span className="admin-kv-label">{k}</span>
          <span>{v ?? '—'}</span>
        </div>
      ))}
    </div>
  );
}

function PersonalBlock({ personal }: { personal: UserProfile['personal'] }) {
  const rows: [string, string, boolean?][] = [
    ['کد ملی', 'national_id'],
    ['نام پدر', 'father_name'],
    ['شماره موبایل', 'mobile'],
    ['مدرک تحصیلی', 'education'],
    ['استان', 'province'],
    ['شهر', 'city'],
    ['جنسیت', 'gender_fa'],
    ['وضعیت تأهل', 'marital_status_fa'],
    ['تاریخ تولد', 'birth_date', true],
    ['سن', 'age'],
    ['آدرس', 'address'],
  ];
  return (
    <div className="admin-card">
      <h3 className="admin-card-title">اطلاعات شخصی کاربر</h3>
      <div className="admin-grid-2">
        {rows.map(([label, key, isDate]) => {
          const raw = personal[key];
          const value =
            raw === null || raw === undefined || raw === ''
              ? '—'
              : isDate
                ? faDate(String(raw))
                : String(raw);
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
