import { useCallback, useEffect, useState } from 'react';
import {
  addCourseLesson,
  addCourseModule,
  addExamQuestion,
  createCourse,
  createCourseExam,
  getCourseDetail,
  getCourses,
  publishCourse,
  type CourseDetailRow,
  type CourseRow,
} from '../../lib/admin';
import { faDate, faMoney } from '../../lib/jalali';
import { Modal, Paged } from './ui';

const PAGE_SIZE = 10;

/** دوره‌های آموزشی — پنل B34: دوره/فصل/درس + آزمون و گواهی (B36). */
export default function CoursesAdmin() {
  const [rows, setRows] = useState<CourseRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [length, setLength] = useState(PAGE_SIZE);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState<CourseDetailRow | null>(null);

  const [form, setForm] = useState({
    title: '',
    slug: '',
    summary: '',
    description: '',
    instructor_name: '',
    is_free: 'yes',
    price: '',
  });

  const load = useCallback(async () => {
    setErr(null);
    try {
      setRows(await getCourses());
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const isFree = form.is_free === 'yes';
      await createCourse({
        title: form.title.trim(),
        slug: form.slug.trim() || null,
        summary: form.summary.trim() || null,
        description: form.description.trim() || null,
        instructor_name: form.instructor_name.trim() || null,
        is_free: isFree,
        price: isFree ? 0 : Number(form.price.replace(/[^\d]/g, '')) || 0,
      });
      setCreating(false);
      setForm({ title: '', slug: '', summary: '', description: '', instructor_name: '', is_free: 'yes', price: '' });
      setMsg('دوره پیش‌نویس ساخته شد؛ برای انتشار حداقل یک درس معتبر لازم است.');
      await load();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function openDetail(c: CourseRow) {
    setErr(null);
    try {
      setDetail(await getCourseDetail(c.id));
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }

  async function doPublish(c: CourseRow) {
    setBusy(true);
    setErr(null);
    try {
      await publishCourse(c.id);
      setMsg(`دوره «${c.title}» منتشر شد.`);
      await load();
      if (detail && detail.id === c.id) setDetail(await getCourseDetail(c.id));
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
      <h2 className="admin-page-title">دوره‌های آموزشی</h2>

      {msg && <div className="admin-ok" style={{ margin: '8px 0' }}>{msg}</div>}
      {err && <div className="admin-error">{err}</div>}

      <div className="admin-card">
        <div className="admin-toolbar" style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <button className="btn-primary" onClick={() => setCreating(true)}>
            + دوره جدید
          </button>
        </div>
        <table className="admin-table">
          <thead>
            <tr>
              <th>عنوان</th>
              <th>مدرس</th>
              <th>قیمت (ریال)</th>
              <th>وضعیت</th>
              <th>انتشار</th>
              <th>عملیات</th>
            </tr>
          </thead>
          <tbody>
            {paged.map((c) => (
              <tr key={c.id}>
                <td>{c.title}</td>
                <td>{c.instructor_name ?? '—'}</td>
                <td className="num">{c.is_free ? 'رایگان' : faMoney(c.price)}</td>
                <td>{c.status === 'published' ? 'منتشرشده' : 'پیش‌نویس'}</td>
                <td>{c.published_at ? faDate(c.published_at, true) : '—'}</td>
                <td>
                  <div style={{ display: 'flex', gap: 4, justifyContent: 'center', flexWrap: 'wrap' }}>
                    <button className="btn-ghost" onClick={() => openDetail(c)}>
                      ساختار دوره
                    </button>
                    {c.status !== 'published' && (
                      <button className="btn-ghost" disabled={busy} onClick={() => doPublish(c)}>
                        انتشار
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {paged.length === 0 && (
              <tr>
                <td colSpan={6} style={{ color: '#6b7280' }}>دوره‌ای ثبت نشده است.</td>
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

      {creating && (
        <Modal title="دوره جدید" onClose={() => setCreating(false)}>
          <form onSubmit={save} className="admin-grid-2">
            <label className="admin-field" style={{ gridColumn: '1 / -1' }}>
              <span>عنوان</span>
              <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required minLength={3} />
            </label>
            <label className="admin-field">
              <span>نامک (اختیاری)</span>
              <input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} style={{ direction: 'ltr' }} />
            </label>
            <label className="admin-field">
              <span>مدرس</span>
              <input value={form.instructor_name} onChange={(e) => setForm({ ...form, instructor_name: e.target.value })} />
            </label>
            <label className="admin-field" style={{ gridColumn: '1 / -1' }}>
              <span>خلاصه</span>
              <input value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} />
            </label>
            <label className="admin-field" style={{ gridColumn: '1 / -1' }}>
              <span>توضیحات</span>
              <textarea
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                rows={4}
                style={{ fontFamily: 'inherit' }}
              />
            </label>
            <label className="admin-field">
              <span>نوع دسترسی</span>
              <select value={form.is_free} onChange={(e) => setForm({ ...form, is_free: e.target.value })}>
                <option value="yes">رایگان</option>
                <option value="no">پولی</option>
              </select>
            </label>
            {form.is_free === 'no' && (
              <label className="admin-field">
                <span>قیمت (ریال)</span>
                <input value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} required />
              </label>
            )}
            {err && <div className="admin-error" style={{ gridColumn: '1 / -1' }}>{err}</div>}
            <div style={{ display: 'flex', gap: 8, gridColumn: '1 / -1' }}>
              <button className="btn-primary" disabled={busy}>
                {busy ? 'در حال ثبت…' : 'ایجاد دوره'}
              </button>
              <button type="button" className="btn-ghost" onClick={() => setCreating(false)}>
                انصراف
              </button>
            </div>
          </form>
        </Modal>
      )}

      {detail && (
        <CourseDetail
          detail={detail}
          onClose={() => setDetail(null)}
          onReload={async () => {
            const fresh = await getCourseDetail(detail.id);
            setDetail(fresh);
            await load();
          }}
          onMsg={setMsg}
        />
      )}
    </div>
  );
}

/** ادیتور ساختار دوره: فصل‌ها/درس‌ها + آزمون‌ها با سؤال‌سازی. */
function CourseDetail({
  detail,
  onClose,
  onReload,
  onMsg,
}: {
  detail: CourseDetailRow;
  onClose: () => void;
  onReload: () => Promise<void>;
  onMsg: (m: string) => void;
}) {
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [moduleTitle, setModuleTitle] = useState('');
  const [lessonFor, setLessonFor] = useState<string | null>(null);
  const [examFor, setExamFor] = useState<string | null>(null);
  const [examForm, setExamForm] = useState({ title: '', pass_score: '60', max_attempts: '1', duration_minutes: '20' });

  async function run(fn: () => Promise<unknown>, okMsg: string) {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      await onReload();
      onMsg(okMsg);
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function addModule() {
    if (moduleTitle.trim().length < 2) {
      setErr('عنوان فصل را وارد کنید');
      return;
    }
    await run(
      () => addCourseModule(detail.id, moduleTitle.trim(), detail.modules.length + 1),
      'فصل افزوده شد.',
    );
    setModuleTitle('');
  }

  async function addExam() {
    if (examForm.title.trim().length < 2) {
      setErr('عنوان آزمون را وارد کنید');
      return;
    }
    await run(
      () =>
        createCourseExam(detail.id, {
          title: examForm.title.trim(),
          pass_score: Number(examForm.pass_score) || 60,
          max_attempts: Number(examForm.max_attempts) || 1,
          duration_minutes: Number(examForm.duration_minutes) || 20,
        }),
      'آزمون افزوده شد.',
    );
    setExamForm({ title: '', pass_score: '60', max_attempts: '1', duration_minutes: '20' });
  }

  return (
    <Modal title={`ساختار «${detail.title}»`} onClose={onClose} wide>
      <div style={{ marginBottom: 10, fontSize: 13 }}>
        وضعیت: <b>{detail.status === 'published' ? 'منتشرشده' : 'پیش‌نویس'}</b>
        {detail.status === 'published' && (
          <span style={{ color: '#6b7280' }}> — ویرایش درس‌های منتشرشده، نسخه جدید درس می‌سازد (B34)</span>
        )}
      </div>
      {err && <div className="admin-error" style={{ marginBottom: 8 }}>{err}</div>}

      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <input
          className="admin-input"
          placeholder="عنوان فصل جدید…"
          value={moduleTitle}
          onChange={(e) => setModuleTitle(e.target.value)}
          style={{ flex: 1, minWidth: 200 }}
        />
        <button className="btn-primary" disabled={busy} onClick={addModule}>
          + فصل
        </button>
      </div>

      {detail.modules.map((m) => (
        <div key={m.id} className="admin-card" style={{ marginBottom: 10, padding: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <b>
              فصل {m.position}: {m.title}
            </b>
            <button className="btn-ghost" onClick={() => setLessonFor(lessonFor === m.id ? null : m.id)}>
              + درس
            </button>
          </div>
          {lessonFor === m.id && (
            <LessonForm
              moduleId={m.id}
              nextPosition={m.lessons.length + 1}
              busy={busy}
              onAdd={(body) => run(() => addCourseLesson(m.id, body), 'درس افزوده شد.')}
              onDone={() => setLessonFor(null)}
            />
          )}
          <table className="admin-table slim">
            <thead>
              <tr>
                <th>#</th>
                <th>درس</th>
                <th>نوع</th>
                <th>مدت (دقیقه)</th>
                <th>فایل</th>
                <th>پیش‌نمایش</th>
                <th>نسخه</th>
              </tr>
            </thead>
            <tbody>
              {m.lessons.map((l) => (
                <tr key={l.id}>
                  <td className="num">{l.position}</td>
                  <td>{l.title}</td>
                  <td>{l.lesson_type === 'video' ? 'ویدیو' : 'PDF'}</td>
                  <td className="num">{Math.round(l.duration_seconds / 60)}</td>
                  <td>{l.has_file ? '✓' : '—'}</td>
                  <td>{l.is_preview ? '✓' : '—'}</td>
                  <td className="num">{l.version}</td>
                </tr>
              ))}
              {m.lessons.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ color: '#6b7280' }}>درسی در این فصل نیست.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      ))}
      {detail.modules.length === 0 && (
        <p style={{ color: '#6b7280' }}>برای این دوره فصلی ثبت نشده است.</p>
      )}

      <h4 style={{ margin: '16px 0 8px' }}>آزمون‌های دوره (B36)</h4>
      <table className="admin-table slim">
        <thead>
          <tr>
            <th>عنوان</th>
            <th>نمره قبولی</th>
            <th>سقف تلاش</th>
            <th>مدت (دقیقه)</th>
            <th>سؤال‌ها</th>
            <th>عملیات</th>
          </tr>
        </thead>
        <tbody>
          {detail.exams.map((e) => (
            <tr key={e.id}>
              <td>{e.title}</td>
              <td className="num">{e.pass_score}</td>
              <td className="num">{e.max_attempts}</td>
              <td className="num">{e.duration_minutes}</td>
              <td className="num">{e.question_count}</td>
              <td>
                <button className="btn-ghost" onClick={() => setExamFor(examFor === e.id ? null : e.id)}>
                  + سؤال
                </button>
              </td>
            </tr>
          ))}
          {detail.exams.length === 0 && (
            <tr>
              <td colSpan={6} style={{ color: '#6b7280' }}>آزمونی ثبت نشده است.</td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="admin-card" style={{ marginTop: 12, padding: 12 }}>
        <h4 style={{ margin: '0 0 8px' }}>افزودن آزمون</h4>
        <div className="admin-grid-2">
          <label className="admin-field">
            <span>عنوان آزمون</span>
            <input value={examForm.title} onChange={(e) => setExamForm({ ...examForm, title: e.target.value })} />
          </label>
          <label className="admin-field">
            <span>نمره قبولی (٪)</span>
            <input type="number" min={0} max={100} value={examForm.pass_score} onChange={(e) => setExamForm({ ...examForm, pass_score: e.target.value })} />
          </label>
          <label className="admin-field">
            <span>سقف تلاش</span>
            <input type="number" min={1} max={10} value={examForm.max_attempts} onChange={(e) => setExamForm({ ...examForm, max_attempts: e.target.value })} />
          </label>
          <label className="admin-field">
            <span>مدت (دقیقه)</span>
            <input type="number" min={1} max={240} value={examForm.duration_minutes} onChange={(e) => setExamForm({ ...examForm, duration_minutes: e.target.value })} />
          </label>
          <div style={{ display: 'flex', gap: 8, gridColumn: '1 / -1' }}>
            <button className="btn-primary" disabled={busy} onClick={addExam}>
              ثبت آزمون
            </button>
          </div>
        </div>
      </div>

      {examFor && (
        <ExamQuestionForm
          examId={examFor}
          busy={busy}
          onAdd={(body) => run(() => addExamQuestion(examFor, body), 'سؤال افزوده شد.')}
          onDone={() => setExamFor(null)}
        />
      )}
    </Modal>
  );
}

/** فرم درس — نوع ویدیو/PDF، مدت، پیش‌نمایش رایگان. */
function LessonForm({
  moduleId,
  nextPosition,
  busy,
  onAdd,
  onDone,
}: {
  moduleId: string;
  nextPosition: number;
  busy: boolean;
  onAdd: (body: { title: string; lesson_type: 'video' | 'pdf'; duration_seconds?: number; position?: number; is_preview?: boolean }) => void;
  onDone: () => void;
}) {
  const [title, setTitle] = useState('');
  const [type, setType] = useState<'video' | 'pdf'>('video');
  const [minutes, setMinutes] = useState('10');
  const [preview, setPreview] = useState(false);

  return (
    <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap', alignItems: 'center' }}>
      <input
        className="admin-input"
        placeholder="عنوان درس…"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        style={{ flex: 2, minWidth: 160 }}
      />
      <select className="admin-select" value={type} onChange={(e) => setType(e.target.value as 'video' | 'pdf')}>
        <option value="video">ویدیو</option>
        <option value="pdf">PDF</option>
      </select>
      <input
        className="admin-input"
        type="number"
        min={0}
        placeholder="دقیقه"
        value={minutes}
        onChange={(e) => setMinutes(e.target.value)}
        style={{ width: 80 }}
      />
      <label style={{ fontSize: 12, display: 'flex', gap: 4, alignItems: 'center' }}>
        <input type="checkbox" checked={preview} onChange={(e) => setPreview(e.target.checked)} />
        پیش‌نمایش رایگان
      </label>
      <button
        className="btn-primary"
        disabled={busy || title.trim().length < 2}
        onClick={() =>
          onAdd({
            title: title.trim(),
            lesson_type: type,
            duration_seconds: (Number(minutes) || 0) * 60,
            position: nextPosition,
            is_preview: preview,
          })
        }
      >
        ثبت درس
      </button>
      <button className="btn-ghost" onClick={onDone}>
        بستن
      </button>
      <span style={{ fontSize: 11, color: '#6b7280', width: '100%' }}>
        فایل درس از بخش فایل‌ها (presigned) متصل می‌شود؛ شناسه فایل در نخستین بارگذاری ثبت می‌گردد.
      </span>
    </div>
  );
}

/** فرم سؤال آزمون — گزینه‌ها با انتخاب پاسخ صحیح. */
function ExamQuestionForm({
  examId,
  busy,
  onAdd,
  onDone,
}: {
  examId: string;
  busy: boolean;
  onAdd: (body: { text: string; options: string[]; correct_index: number; position?: number }) => void;
  onDone: () => void;
}) {
  const [text, setText] = useState('');
  const [opts, setOpts] = useState(['', '', '', '']);
  const [correct, setCorrect] = useState(0);

  return (
    <div className="admin-card" style={{ marginTop: 10, padding: 12 }}>
      <h4 style={{ margin: '0 0 8px' }}>افزودن سؤال به آزمون</h4>
      <label className="admin-field" style={{ marginBottom: 8 }}>
        <span>متن سؤال</span>
        <input value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      {opts.map((o, i) => (
        <div key={i} style={{ display: 'flex', gap: 6, marginBottom: 6, alignItems: 'center' }}>
          <input
            type="radio"
            name={`correct-${examId}`}
            checked={correct === i}
            onChange={() => setCorrect(i)}
            title="پاسخ صحیح"
          />
          <input
            className="admin-input"
            placeholder={`گزینه ${i + 1}`}
            value={o}
            onChange={(e) => setOpts(opts.map((x, j) => (j === i ? e.target.value : x)))}
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
        <button type="button" className="btn-ghost" onClick={() => setOpts([...opts, ''])} disabled={opts.length >= 6}>
          + گزینه
        </button>
        <button
          type="button"
          className="btn-primary"
          disabled={busy || text.trim().length < 3 || opts.some((o) => !o.trim())}
          onClick={() => {
            onAdd({ text: text.trim(), options: opts.map((o) => o.trim()), correct_index: correct });
            setText('');
            setOpts(['', '', '', '']);
            setCorrect(0);
            onDone();
          }}
        >
          ثبت سؤال
        </button>
        <button type="button" className="btn-ghost" onClick={onDone}>
          بستن
        </button>
      </div>
    </div>
  );
}
