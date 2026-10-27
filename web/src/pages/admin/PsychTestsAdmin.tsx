import { useCallback, useEffect, useState } from 'react';
import {
  addPsychQuestion,
  addPsychRule,
  approvePsychVersion,
  createPsychTest,
  createPsychVersion,
  getPsychReviewQueue,
  getPsychTestsManage,
  getPsychVersion,
  publishPsychVersion,
  reviewPsychAttempt,
  type PsychAttemptRow,
  type PsychTestRow,
  type PsychVersionDetail,
  type PsychVersionRow,
} from '../../lib/admin';
import { faDate } from '../../lib/jalali';
import { Modal, Paged } from './ui';

const PAGE_SIZE = 10;

/** وضعیت نسخه/آزمون با برچسب فارسی و رنگ. */
const STATUS_FA: Record<string, string> = {
  draft: 'پیش‌نویس',
  approved: 'تأیید علمی',
  published: 'منتشرشده',
  archived: 'آرشیو',
};

const ATTEMPT_STATUS_FA: Record<string, string> = {
  started: 'شروع‌شده',
  consented: 'رضایت ثبت‌شده',
  in_progress: 'در جریان',
  scored: 'نمره‌گذاری‌شده',
  reviewed: 'بازبینی‌شده',
  abandoned: 'رهاشده',
};

/** آزمون‌های روان‌شناسی — پنل B37: مدیریت نسخه‌دار + صف بازبینی ناظر علمی. */
export default function PsychTestsAdmin() {
  const [tab, setTab] = useState<'tests' | 'queue'>('tests');
  const [rows, setRows] = useState<PsychTestRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [length, setLength] = useState(PAGE_SIZE);

  // create-test modal
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    code: '',
    title: '',
    purpose: '',
    target_population: '',
    age_min: '',
    age_max: '',
    scientific_doc: '',
  });

  // versions modal
  const [versionsOf, setVersionsOf] = useState<PsychTestRow | null>(null);
  const [newScale, setNewScale] = useState('');
  const [detail, setDetail] = useState<PsychVersionDetail | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      setRows(await getPsychTestsManage());
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function submitCreate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await createPsychTest({
        code: form.code.trim(),
        title: form.title.trim(),
        purpose: form.purpose.trim() || null,
        target_population: form.target_population.trim() || null,
        age_min: form.age_min ? Number(form.age_min) : null,
        age_max: form.age_max ? Number(form.age_max) : null,
        scientific_doc: form.scientific_doc.trim() || null,
      });
      setCreating(false);
      setForm({ code: '', title: '', purpose: '', target_population: '', age_min: '', age_max: '', scientific_doc: '' });
      setMsg('آزمون با نسخه پیش‌نویس اولیه ایجاد شد.');
      await load();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function openVersions(t: PsychTestRow) {
    setVersionsOf(t);
    setDetail(null);
    setNewScale('');
  }

  async function addVersion() {
    if (!versionsOf || newScale.trim().length < 2) {
      setErr('برچسب مقیاس را وارد کنید (حداقل ۲ نویسه)');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await createPsychVersion(versionsOf.id, newScale.trim());
      setNewScale('');
      const fresh = await getPsychTestsManage();
      setRows(fresh);
      setVersionsOf(fresh.find((x) => x.id === versionsOf.id) ?? versionsOf);
      setMsg('نسخه پیش‌نویس جدید ساخته شد.');
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function openDetail(v: PsychVersionRow) {
    setErr(null);
    try {
      setDetail(await getPsychVersion(v.id));
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }

  async function versionAction(v: PsychVersionDetail, action: 'approve' | 'publish') {
    setBusy(true);
    setErr(null);
    try {
      if (action === 'approve') await approvePsychVersion(v.id);
      else await publishPsychVersion(v.id);
      setMsg(action === 'approve' ? 'تأیید علمی ثبت شد.' : 'نسخه منتشر شد؛ نسخه پیشین آرشیو گردید.');
      setDetail(await getPsychVersion(v.id));
      const fresh = await getPsychTestsManage();
      setRows(fresh);
      if (versionsOf) setVersionsOf(fresh.find((x) => x.id === versionsOf.id) ?? versionsOf);
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const pageSize = length === -1 ? Math.max(rows.length, 1) : length;
  const paged = rows.slice(page * pageSize, (page + 1) * pageSize);

  return (
    <div className="admin-page">
      <h2 className="admin-page-title">آزمون‌های روان‌شناسی (ارزیابی)</h2>

      <div className="admin-toolbar" style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <button
          className={tab === 'tests' ? 'btn-primary' : 'btn-ghost'}
          onClick={() => setTab('tests')}
        >
          مدیریت آزمون‌ها
        </button>
        <button
          className={tab === 'queue' ? 'btn-primary' : 'btn-ghost'}
          onClick={() => setTab('queue')}
        >
          صف بازبینی ناظر علمی
        </button>
      </div>

      {msg && <div className="admin-ok" style={{ margin: '8px 0' }}>{msg}</div>}
      {err && <div className="admin-error">{err}</div>}

      {tab === 'tests' && (
        <div className="admin-card">
          <div className="admin-toolbar" style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <button className="btn-primary" onClick={() => setCreating(true)}>
              + آزمون جدید
            </button>
          </div>
          <table className="admin-table">
            <thead>
              <tr>
                <th>کد</th>
                <th>عنوان</th>
                <th>جامعه هدف</th>
                <th>بازه سنی</th>
                <th>وضعیت</th>
                <th>نسخه‌ها</th>
                <th>عملیات</th>
              </tr>
            </thead>
            <tbody>
              {paged.map((t) => (
                <tr key={t.id}>
                  <td style={{ direction: 'ltr' }}>{t.code}</td>
                  <td>{t.title}</td>
                  <td>{t.target_population ?? '—'}</td>
                  <td className="num">
                    {t.age_min !== null || t.age_max !== null
                      ? `${t.age_min ?? '−'} تا ${t.age_max ?? '−'}`
                      : '—'}
                  </td>
                  <td>{STATUS_FA[t.status] ?? t.status}</td>
                  <td>
                    {t.versions.length === 0
                      ? '—'
                      : `${t.versions.length} نسخه (آخر: ${STATUS_FA[t.versions[t.versions.length - 1].status] ?? ''})`}
                  </td>
                  <td>
                    <button className="btn-ghost" onClick={() => openVersions(t)}>
                      نسخه‌ها
                    </button>
                  </td>
                </tr>
              ))}
              {paged.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ color: '#6b7280' }}>
                    آزمونی ثبت نشده است.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <Paged
            page={page}
            length={length}
            filtered={rows.length}
            onPage={setPage}
            onLength={(l) => {
              setLength(l);
              setPage(0);
            }}
          />
        </div>
      )}

      {tab === 'tests' && versionsOf && (
        <Modal title={`نسخه‌های «${versionsOf.title}»`} onClose={() => setVersionsOf(null)} wide>
          <div style={{ marginBottom: 12, fontSize: 12, color: '#6b7280' }}>
            نسخه منتشرشده تغییرناپذیر است؛ برای اصلاح، نسخه جدید بسازید. انتشار تنها پس از تأیید
            علمی ناظر مجاز است (B37).
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
            <input
              className="admin-input"
              placeholder="برچسب مقیاس نسخه جدید؛ مثلاً لیکرت چهاردرجه‌ای"
              value={newScale}
              onChange={(e) => setNewScale(e.target.value)}
              style={{ flex: 1, minWidth: 220 }}
            />
            <button className="btn-primary" disabled={busy} onClick={addVersion}>
              + نسخه جدید
            </button>
          </div>
          <table className="admin-table slim">
            <thead>
              <tr>
                <th>نسخه</th>
                <th>مقیاس</th>
                <th>وضعیت</th>
                <th>تأیید علمی</th>
                <th>انتشار</th>
                <th>عملیات</th>
              </tr>
            </thead>
            <tbody>
              {versionsOf.versions.map((v) => (
                <tr key={v.id}>
                  <td className="num">{v.version}</td>
                  <td>{v.scale_label}</td>
                  <td>{STATUS_FA[v.status] ?? v.status}</td>
                  <td>{v.approved_at ? faDate(v.approved_at, true) : '—'}</td>
                  <td>{v.published_at ? faDate(v.published_at, true) : '—'}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'center' }}>
                      <button className="btn-ghost" onClick={() => openDetail(v)}>
                        سؤال‌ها و قواعد
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {versionsOf.versions.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ color: '#6b7280' }}>
                    برای این آزمون نسخه‌ای ثبت نشده است.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </Modal>
      )}

      {tab === 'tests' && versionsOf && detail && (
        <Modal
          title={`نسخه ${detail.version} — ${versionsOf.title}`}
          onClose={() => setDetail(null)}
          wide
        >
          <div style={{ marginBottom: 10 }}>
            وضعیت: <b>{STATUS_FA[detail.status] ?? detail.status}</b> · مقیاس: {detail.scale_label}
          </div>
          {detail.status === 'draft' && (
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <button className="btn-primary" disabled={busy} onClick={() => versionAction(detail, 'approve')}>
                ثبت تأیید علمی
              </button>
            </div>
          )}
          {detail.status === 'approved' && (
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <button className="btn-primary" disabled={busy} onClick={() => versionAction(detail, 'publish')}>
                انتشار نسخه
              </button>
            </div>
          )}

          <h4 style={{ margin: '12px 0 6px' }}>سؤال‌ها ({detail.questions.length})</h4>
          <table className="admin-table slim">
            <thead>
              <tr>
                <th>#</th>
                <th>متن سؤال</th>
                <th>گزینه‌ها (نمره)</th>
              </tr>
            </thead>
            <tbody>
              {detail.questions.map((q) => (
                <tr key={q.id}>
                  <td className="num">{q.position}</td>
                  <td>{q.text}</td>
                  <td style={{ fontSize: 12 }}>
                    {q.options.map((o) => `${o.label} (${o.score})`).join(' · ')}
                  </td>
                </tr>
              ))}
              {detail.questions.length === 0 && (
                <tr>
                  <td colSpan={3} style={{ color: '#6b7280' }}>سؤالی ثبت نشده است.</td>
                </tr>
              )}
            </tbody>
          </table>
          {detail.status === 'draft' && <QuestionForm versionId={detail.id} onDone={() => openDetail(detail)} />}

          <h4 style={{ margin: '16px 0 6px' }}>قواعد تفسیر ({detail.rules.length})</h4>
          <table className="admin-table slim">
            <thead>
              <tr>
                <th>بازه نمره</th>
                <th>عنوان تفسیر</th>
                <th>توصیه</th>
                <th>وضعیت</th>
              </tr>
            </thead>
            <tbody>
              {detail.rules.map((r) => (
                <tr key={r.id}>
                  <td className="num">{r.min_score} تا {r.max_score}</td>
                  <td>{r.title}</td>
                  <td style={{ fontSize: 12 }}>{r.guidance}</td>
                  <td>{STATUS_FA[r.status] ?? r.status}</td>
                </tr>
              ))}
              {detail.rules.length === 0 && (
                <tr>
                  <td colSpan={4} style={{ color: '#6b7280' }}>
                    بدون قاعده تفسیر، تأیید علمی ممکن نیست.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {detail.status === 'draft' && <RuleForm versionId={detail.id} onDone={() => openDetail(detail)} />}
        </Modal>
      )}

      {tab === 'tests' && creating && (
        <Modal title="آزمون جدید" onClose={() => setCreating(false)}>
          <form onSubmit={submitCreate} className="admin-grid-2">
            <label className="admin-field">
              <span>کد (لاتین، یکتا)</span>
              <input
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value })}
                placeholder="beck-anxiety-b2"
                required
                style={{ direction: 'ltr' }}
              />
            </label>
            <label className="admin-field">
              <span>عنوان</span>
              <input
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="آزمون اضطراب بک-۲"
                required
              />
            </label>
            <label className="admin-field" style={{ gridColumn: '1 / -1' }}>
              <span>هدف آزمون</span>
              <input
                value={form.purpose}
                onChange={(e) => setForm({ ...form, purpose: e.target.value })}
                placeholder="سنجش شدت نشانه‌های اضطراب"
              />
            </label>
            <label className="admin-field" style={{ gridColumn: '1 / -1' }}>
              <span>جامعه هدف</span>
              <input
                value={form.target_population}
                onChange={(e) => setForm({ ...form, target_population: e.target.value })}
                placeholder="بزرگسالان ۱۸ تا ۶۰ سال"
              />
            </label>
            <label className="admin-field">
              <span>حداقل سن</span>
              <input
                type="number"
                min={0}
                max={120}
                value={form.age_min}
                onChange={(e) => setForm({ ...form, age_min: e.target.value })}
              />
            </label>
            <label className="admin-field">
              <span>حداکثر سن</span>
              <input
                type="number"
                min={0}
                max={120}
                value={form.age_max}
                onChange={(e) => setForm({ ...form, age_max: e.target.value })}
              />
            </label>
            <label className="admin-field" style={{ gridColumn: '1 / -1' }}>
              <span>مستند علمی (نظریه/هنجار)</span>
              <input
                value={form.scientific_doc}
                onChange={(e) => setForm({ ...form, scientific_doc: e.target.value })}
                placeholder="Beck, 1988 — manual"
              />
            </label>
            {err && <div className="admin-error" style={{ gridColumn: '1 / -1' }}>{err}</div>}
            <div style={{ display: 'flex', gap: 8, gridColumn: '1 / -1' }}>
              <button className="btn-primary" disabled={busy}>
                {busy ? 'در حال ثبت…' : 'ایجاد آزمون'}
              </button>
              <button type="button" className="btn-ghost" onClick={() => setCreating(false)}>
                انصراف
              </button>
            </div>
            <p style={{ gridColumn: '1 / -1', fontSize: 12, color: '#6b7280' }}>
              رضایت‌نامه با kind پیش‌فرض «psych_test» الزامی است؛ اجرا بدون رضایت معتبر آغاز نمی‌شود.
            </p>
          </form>
        </Modal>
      )}

      {tab === 'queue' && <ReviewQueue />}
    </div>
  );
}

/** افزودن سؤال به نسخه پیش‌نویس — گزینه‌ها با نمره ۰ تا ۱۰۰. */
function QuestionForm({ versionId, onDone }: { versionId: string; onDone: () => void }) {
  const [text, setText] = useState('');
  const [opts, setOpts] = useState([
    { label: 'هیچ', score: '0' },
    { label: 'کم', score: '1' },
    { label: 'متوسط', score: '2' },
    { label: 'زیاد', score: '3' },
  ]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (text.trim().length < 3) {
      setErr('متن سؤال را وارد کنید');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await addPsychQuestion(versionId, {
        text: text.trim(),
        options: opts
          .filter((o) => o.label.trim())
          .map((o) => ({ label: o.label.trim(), score: Number(o.score) || 0 })),
      });
      setText('');
      onDone();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-card" style={{ marginTop: 10 }}>
      <h4 style={{ margin: '0 0 8px' }}>افزودن سؤال</h4>
      <label className="admin-field" style={{ marginBottom: 8 }}>
        <span>متن سؤال</span>
        <input value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      {opts.map((o, i) => (
        <div key={i} style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
          <input
            className="admin-input"
            value={o.label}
            placeholder={`برچسب گزینه ${i + 1}`}
            onChange={(e) => setOpts(opts.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))}
            style={{ flex: 2 }}
          />
          <input
            className="admin-input"
            type="number"
            min={0}
            max={100}
            value={o.score}
            onChange={(e) => setOpts(opts.map((x, j) => (j === i ? { ...x, score: e.target.value } : x)))}
            style={{ flex: 1 }}
          />
          <button
            type="button"
            className="btn-ghost"
            onClick={() => setOpts(opts.filter((_, j) => j !== i))}
            disabled={opts.length <= 2}
          >
            ✕
          </button>
        </div>
      ))}
      <div style={{ display: 'flex', gap: 8 }}>
        <button type="button" className="btn-ghost" onClick={() => setOpts([...opts, { label: '', score: '0' }])}>
          + گزینه
        </button>
        <button type="button" className="btn-primary" disabled={busy} onClick={submit}>
          {busy ? 'در حال ثبت…' : 'ثبت سؤال'}
        </button>
      </div>
      {err && <div className="admin-error" style={{ marginTop: 8 }}>{err}</div>}
    </div>
  );
}

/** افزودن قاعده تفسیر — تفسیر فقط از قاعده مصوب ناظر علمی تولید می‌شود. */
function RuleForm({ versionId, onDone }: { versionId: string; onDone: () => void }) {
  const [form, setForm] = useState({ min_score: '', max_score: '', title: '', guidance: '' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await addPsychRule(versionId, {
        min_score: Number(form.min_score),
        max_score: Number(form.max_score),
        title: form.title.trim(),
        guidance: form.guidance.trim(),
      });
      setForm({ min_score: '', max_score: '', title: '', guidance: '' });
      onDone();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const f = (label: string, key: keyof typeof form, props: Record<string, unknown> = {}) => (
    <label className="admin-field">
      <span>{label}</span>
      <input
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        {...props}
      />
    </label>
  );

  return (
    <div className="admin-card" style={{ marginTop: 10 }}>
      <h4 style={{ margin: '0 0 8px' }}>افزودن قاعده تفسیر</h4>
      <div className="admin-grid-2">
        {f('حداقل نمره', 'min_score', { type: 'number', min: 0 })}
        {f('حداکثر نمره', 'max_score', { type: 'number', min: 0 })}
        {f('عنوان تفسیر', 'title', { placeholder: 'اضطراب متوسط' })}
        {f('توصیه', 'guidance', { placeholder: 'مشاوره تکمیلی توصیه می‌شود.' })}
        <div style={{ display: 'flex', gap: 8, gridColumn: '1 / -1' }}>
          <button type="button" className="btn-primary" disabled={busy} onClick={submit}>
            {busy ? 'در حال ثبت…' : 'ثبت قاعده'}
          </button>
        </div>
        {err && <div className="admin-error" style={{ gridColumn: '1 / -1' }}>{err}</div>}
      </div>
    </div>
  );
}

/** صف بازبینی ناظر علمی — دسترسی به نتیجه دیگران در audit.access_events ثبت می‌شود. */
function ReviewQueue() {
  const [rows, setRows] = useState<PsychAttemptRow[]>([]);
  const [status, setStatus] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [length, setLength] = useState(PAGE_SIZE);
  const [reviewing, setReviewing] = useState<PsychAttemptRow | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (st: string) => {
    setErr(null);
    try {
      setRows(await getPsychReviewQueue(st));
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }, []);

  useEffect(() => {
    load('');
  }, [load]);

  async function submitReview() {
    if (!reviewing) return;
    setBusy(true);
    setErr(null);
    try {
      await reviewPsychAttempt(reviewing.id, note.trim() || undefined);
      setReviewing(null);
      setNote('');
      setMsg('بازبینی ثبت شد؛ اجرا به وضعیت «بازبینی‌شده» رفت.');
      await load(status);
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const pageSize = length === -1 ? Math.max(rows.length, 1) : length;
  const paged = rows.slice(page * pageSize, (page + 1) * pageSize);

  return (
    <div className="admin-card">
      <div className="admin-toolbar" style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <select
          className="admin-select"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(0);
            load(e.target.value);
          }}
        >
          <option value="">همه وضعیت‌ها</option>
          <option value="scored">نمره‌گذاری‌شده (در انتظار بازبینی)</option>
          <option value="reviewed">بازبینی‌شده</option>
          <option value="in_progress">در جریان</option>
          <option value="abandoned">رهاشده</option>
        </select>
      </div>
      {msg && <div className="admin-ok" style={{ margin: '8px 0' }}>{msg}</div>}
      {err && <div className="admin-error">{err}</div>}
      <table className="admin-table">
        <thead>
          <tr>
            <th>اجرای آزمون</th>
            <th>وضعیت</th>
            <th>نمره خام</th>
            <th>تفسیر</th>
            <th>ارسال</th>
            <th>یادداشت بازبینی</th>
            <th>عملیات</th>
          </tr>
        </thead>
        <tbody>
          {paged.map((a) => (
            <tr key={a.id}>
              <td style={{ direction: 'ltr', fontSize: 11 }}>{a.id.slice(0, 8)}…</td>
              <td>{ATTEMPT_STATUS_FA[a.status] ?? a.status}</td>
              <td className="num">{a.raw_score ?? '—'}</td>
              <td>{a.interpretation_title ?? '—'}</td>
              <td>{a.submitted_at ? faDate(a.submitted_at, true) : '—'}</td>
              <td style={{ fontSize: 12 }}>{a.review_note ?? '—'}</td>
              <td>
                {a.status === 'scored' && (
                  <button className="btn-ghost" onClick={() => setReviewing(a)}>
                    بازبینی
                  </button>
                )}
              </td>
            </tr>
          ))}
          {paged.length === 0 && (
            <tr>
              <td colSpan={7} style={{ color: '#6b7280' }}>
                اجرایی در این فیلتر وجود ندارد.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <Paged
        page={page}
        length={length}
        filtered={rows.length}
        onPage={setPage}
        onLength={(l) => {
          setLength(l);
          setPage(0);
        }}
      />

      {reviewing && (
        <Modal title={`بازبینی اجرای ${reviewing.id.slice(0, 8)}…`} onClose={() => setReviewing(null)}>
          <div style={{ marginBottom: 10 }}>
            نمره خام: <b>{reviewing.raw_score ?? '—'}</b> · تفسیر مصوب:{' '}
            <b>{reviewing.interpretation_title ?? '—'}</b>
          </div>
          <p style={{ fontSize: 12, color: '#6b7280', lineHeight: 2 }}>
            {reviewing.interpretation_text ?? ''}
          </p>
          <label className="admin-field">
            <span>یادداشت بازبینی (اختیاری)</span>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="تفسیر مطابق مصوبه نسخه بررسی شد."
            />
          </label>
          {err && <div className="admin-error" style={{ marginTop: 8 }}>{err}</div>}
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button className="btn-primary" disabled={busy} onClick={submitReview}>
              {busy ? 'در حال ثبت…' : 'ثبت بازبینی'}
            </button>
            <button className="btn-ghost" onClick={() => setReviewing(null)}>
              انصراف
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
