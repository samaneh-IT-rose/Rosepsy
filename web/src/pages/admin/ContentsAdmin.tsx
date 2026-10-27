import { useCallback, useEffect, useState } from 'react';
import {
  contentTransition,
  createContent,
  getContents,
  getContent,
  getTopics,
  updateContent,
  type ContentRow,
  type TopicRow,
} from '../../lib/admin';
import { faDate } from '../../lib/jalali';
import { Modal, Paged } from './ui';

const PAGE_SIZE = 10;

const TYPE_FA: Record<string, string> = {
  article: 'مقاله',
  news: 'خبر',
  podcast: 'پادکست',
  video: 'ویدیو',
};

const STATUS_FA: Record<string, string> = {
  draft: 'پیش‌نویس',
  in_review: 'در بازبینی',
  published: 'منتشرشده',
  rejected: 'ردشده',
  archived: 'آرشیو',
};

/** اقدامات مجاز هر وضعیت — مطابق ماشین حالت B33. */
const ACTIONS: Record<string, { key: 'submit-review' | 'publish' | 'reject' | 'archive' | 'back-to-draft'; label: string }[]> = {
  draft: [{ key: 'submit-review', label: 'ارجاع به بازبینی' }],
  in_review: [
    { key: 'publish', label: 'انتشار' },
    { key: 'reject', label: 'رد' },
  ],
  published: [{ key: 'archive', label: 'آرشیو' }],
  rejected: [{ key: 'back-to-draft', label: 'بازگشت به پیش‌نویس' }],
  archived: [{ key: 'back-to-draft', label: 'بازگشت به پیش‌نویس' }],
};

const EMPTY_FORM = {
  type: 'article',
  title: '',
  slug: '',
  summary: '',
  body: '',
  source: '',
  seo_title: '',
  seo_description: '',
  topic_ids: [] as string[],
};

/** مدیریت محتوا — چرخه انتشار CMS با نسخه‌های تغییرناپذیر (B33). */
export default function ContentsAdmin() {
  const [rows, setRows] = useState<ContentRow[]>([]);
  const [topics, setTopics] = useState<TopicRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(0);
  const [length, setLength] = useState(PAGE_SIZE);

  const [editing, setEditing] = useState<ContentRow | 'new' | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [revisions, setRevisions] = useState<ContentRow | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setErr(null);
    try {
      setRows(await getContents());
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
    getTopics().then(setTopics).catch(() => setTopics([]));
  }, [load]);

  function openNew() {
    setForm(EMPTY_FORM);
    setEditing('new');
  }

  function openEdit(c: ContentRow) {
    setForm({
      type: c.type,
      title: c.title,
      slug: c.slug,
      summary: c.summary ?? '',
      body: c.body ?? '',
      source: c.source ?? '',
      seo_title: c.seo_title ?? '',
      seo_description: c.seo_description ?? '',
      topic_ids: [],
    });
    setEditing(c);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const body = {
      type: form.type,
      title: form.title.trim(),
      slug: form.slug.trim() || null,
      summary: form.summary.trim() || null,
      body: form.body.trim() || null,
      source: form.source.trim() || null,
      seo_title: form.seo_title.trim() || null,
      seo_description: form.seo_description.trim() || null,
      topic_ids: form.topic_ids,
    };
    try {
      if (editing === 'new') await createContent(body);
      else if (editing) await updateContent(editing.id, body);
      setEditing(null);
      setMsg('محتوا ذخیره شد؛ هر ذخیره یک نسخه تغییرناپذیر جدید می‌سازد.');
      await load();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function act(c: ContentRow, key: 'submit-review' | 'publish' | 'reject' | 'archive' | 'back-to-draft') {
    setBusy(true);
    setErr(null);
    try {
      await contentTransition(c.id, key);
      setMsg(`«${c.title}» → ${STATUS_FA[key === 'submit-review' ? 'in_review' : key === 'back-to-draft' ? 'draft' : key]}`);
      await load();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function openRevisions(c: ContentRow) {
    setErr(null);
    try {
      setRevisions(await getContent(c.id));
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }

  const filtered = rows.filter(
    (r) =>
      (!statusFilter || r.status === statusFilter) &&
      (!q.trim() || r.title.includes(q.trim()) || r.slug.includes(q.trim())),
  );
  const pageSize = length === -1 ? Math.max(filtered.length, 1) : length;
  const paged = filtered.slice(page * pageSize, (page + 1) * pageSize);

  return (
    <div className="admin-page">
      <h2 className="admin-page-title">مدیریت محتوا (CMS)</h2>

      {msg && <div className="admin-ok" style={{ margin: '8px 0' }}>{msg}</div>}
      {err && <div className="admin-error">{err}</div>}

      <div className="admin-card">
        <div className="admin-toolbar" style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
          <select
            className="admin-select"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(0);
            }}
          >
            <option value="">همه وضعیت‌ها</option>
            {Object.entries(STATUS_FA).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <input
            className="admin-input"
            placeholder="جست‌وجوی عنوان/نامک…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ flex: 1, minWidth: 200 }}
          />
          <button className="btn-primary" onClick={openNew}>
            + محتوای جدید
          </button>
        </div>

        <table className="admin-table">
          <thead>
            <tr>
              <th>نوع</th>
              <th>عنوان</th>
              <th>نامک</th>
              <th>موضوعات</th>
              <th>وضعیت</th>
              <th>انتشار</th>
              <th>عملیات</th>
            </tr>
          </thead>
          <tbody>
            {paged.map((c) => (
              <tr key={c.id}>
                <td>{TYPE_FA[c.type] ?? c.type}</td>
                <td>{c.title}</td>
                <td style={{ direction: 'ltr', fontSize: 11 }}>{c.slug}</td>
                <td style={{ fontSize: 12 }}>{c.topics.length ? c.topics.join('، ') : '—'}</td>
                <td>{STATUS_FA[c.status] ?? c.status}</td>
                <td>{c.published_at ? faDate(c.published_at, true) : '—'}</td>
                <td>
                  <div style={{ display: 'flex', gap: 4, justifyContent: 'center', flexWrap: 'wrap' }}>
                    <button className="btn-ghost" onClick={() => openEdit(c)}>
                      ویرایش
                    </button>
                    <button className="btn-ghost" onClick={() => openRevisions(c)}>
                      نسخه‌ها
                    </button>
                    {(ACTIONS[c.status] ?? []).map((a) => (
                      <button key={a.key} className="btn-ghost" disabled={busy} onClick={() => act(c, a.key)}>
                        {a.label}
                      </button>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
            {paged.length === 0 && (
              <tr>
                <td colSpan={7} style={{ color: '#6b7280' }}>
                  محتوایی ثبت نشده است.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <Paged
          page={page}
          length={length}
          filtered={filtered.length}
          onPage={setPage}
          onLength={(l) => {
            setLength(l);
            setPage(0);
          }}
        />
      </div>

      {editing && (
        <Modal
          title={editing === 'new' ? 'محتوای جدید' : `ویرایش «${editing.title}»`}
          onClose={() => setEditing(null)}
          wide
        >
          <form onSubmit={save} className="admin-grid-2">
            <label className="admin-field">
              <span>نوع</span>
              <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
                {Object.entries(TYPE_FA).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </label>
            <label className="admin-field">
              <span>عنوان</span>
              <input
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                required
                minLength={3}
              />
            </label>
            <label className="admin-field">
              <span>نامک (اختیاری — خودکار ساخته می‌شود)</span>
              <input
                value={form.slug}
                onChange={(e) => setForm({ ...form, slug: e.target.value })}
                style={{ direction: 'ltr' }}
              />
            </label>
            <label className="admin-field">
              <span>منبع</span>
              <input value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} />
            </label>
            <label className="admin-field" style={{ gridColumn: '1 / -1' }}>
              <span>خلاصه</span>
              <input value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} />
            </label>
            <label className="admin-field" style={{ gridColumn: '1 / -1' }}>
              <span>متن محتوا</span>
              <textarea
                value={form.body}
                onChange={(e) => setForm({ ...form, body: e.target.value })}
                rows={6}
                style={{ fontFamily: 'inherit' }}
              />
            </label>
            <label className="admin-field">
              <span>عنوان SEO</span>
              <input value={form.seo_title} onChange={(e) => setForm({ ...form, seo_title: e.target.value })} />
            </label>
            <label className="admin-field">
              <span>توضیح SEO</span>
              <input
                value={form.seo_description}
                onChange={(e) => setForm({ ...form, seo_description: e.target.value })}
              />
            </label>
            {topics.length > 0 && (
              <div className="admin-field" style={{ gridColumn: '1 / -1' }}>
                <span>موضوعات</span>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {topics.map((t) => (
                    <label key={t.id} style={{ fontSize: 12, display: 'flex', gap: 4, alignItems: 'center' }}>
                      <input
                        type="checkbox"
                        checked={form.topic_ids.includes(t.id)}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            topic_ids: e.target.checked
                              ? [...form.topic_ids, t.id]
                              : form.topic_ids.filter((x) => x !== t.id),
                          })
                        }
                      />
                      {t.name}
                    </label>
                  ))}
                </div>
              </div>
            )}
            {err && <div className="admin-error" style={{ gridColumn: '1 / -1' }}>{err}</div>}
            <div style={{ display: 'flex', gap: 8, gridColumn: '1 / -1' }}>
              <button className="btn-primary" disabled={busy}>
                {busy ? 'در حال ذخیره…' : 'ذخیره'}
              </button>
              <button type="button" className="btn-ghost" onClick={() => setEditing(null)}>
                انصراف
              </button>
            </div>
          </form>
        </Modal>
      )}

      {revisions && (
        <Modal title={`نسخه‌های «${revisions.title}»`} onClose={() => setRevisions(null)} wide>
          <table className="admin-table slim">
            <thead>
              <tr>
                <th>نسخه</th>
                <th>تاریخ</th>
                <th>وضعیت لحظه‌ای</th>
                <th>عنوان در نسخه</th>
              </tr>
            </thead>
            <tbody>
              {(revisions.revisions ?? []).map((r) => (
                <tr key={r.version}>
                  <td className="num">{r.version}</td>
                  <td>{faDate(r.created_at, true)}</td>
                  <td>{STATUS_FA[String(r.snapshot?.status ?? '')] ?? '—'}</td>
                  <td>{String(r.snapshot?.title ?? '—')}</td>
                </tr>
              ))}
              {(revisions.revisions ?? []).length === 0 && (
                <tr>
                  <td colSpan={4} style={{ color: '#6b7280' }}>نسخه‌ای ثبت نشده است.</td>
                </tr>
              )}
            </tbody>
          </table>
        </Modal>
      )}
    </div>
  );
}
