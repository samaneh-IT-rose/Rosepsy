import { useCallback, useEffect, useState } from 'react';
import { api } from '../lib/api';

type PsychTest = {
  id: string;
  code: string;
  title: string;
  purpose: string | null;
  target_population: string | null;
  age_min: number | null;
  age_max: number | null;
  scientific_doc: string | null;
  published_version: { id: string; version: number; scale_label: string } | null;
};

type Question = {
  id: string;
  text: string;
  position: number;
  options: { label: string }[];
  answered_index: number | null;
};

type Attempt = {
  id: string;
  status: string;
  raw_score?: number | null;
  interpretation_title?: string | null;
  interpretation_text?: string | null;
  rule_id?: string | null;
};

type MyResult = Attempt & { submitted_at?: string | null };

const STATUS_FA: Record<string, string> = {
  started: 'آماده رضایت',
  consented: 'در انتظار پاسخ',
  in_progress: 'در حال پاسخ‌گویی',
  scored: 'نمره‌گذاری‌شده',
  reviewed: 'بازبینی‌شده توسط ناظر علمی',
  abandoned: 'رهاشده',
};

const card: React.CSSProperties = {
  border: '1px solid #e5e7eb',
  borderRadius: 12,
  background: '#fff',
  padding: 14,
  marginBottom: 10,
  textAlign: 'right',
};

/** تست‌های روان‌شناسی (B37): کاتالوگ، معرفی، رضایت، اجرا و نتایج من. */
export default function PsychTests() {
  const [tests, setTests] = useState<PsychTest[]>([]);
  const [results, setResults] = useState<MyResult[]>([]);
  const [selected, setSelected] = useState<PsychTest | null>(null);
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [agree, setAgree] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [t, r] = await Promise.all([
        api.request<PsychTest[]>('/psych-tests'),
        api.request<MyResult[]>('/me/psych-results'),
      ]);
      setTests(t);
      setResults(r);
    } catch {
      setMsg('خطا در دریافت آزمون‌ها');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function start(t: PsychTest) {
    setMsg(null);
    setSelected(t);
    setAttempt(null);
    setQuestions([]);
    setAnswers({});
    setAgree(false);
    try {
      const a = await api.request<Attempt>(`/psych-tests/${t.id}/attempts`, { method: 'POST' });
      setAttempt(a);
    } catch (ex) {
      setMsg((ex as Error).message || 'خطا در شروع آزمون');
    }
  }

  async function grantConsentAndContinue() {
    if (!selected || !attempt) return;
    setBusy(true);
    setMsg(null);
    try {
      // رضایت از طریق B41 (اگر قبلاً رضایت فعال داشته باشد ۴۰۹ می‌گیرد و مهم نیست)
      try {
        await api.request('/consents', {
          method: 'POST',
          body: JSON.stringify({ kind: 'psych_test' }),
        });
      } catch {
        /* already granted */
      }
      const a = await api.request<Attempt>(`/psych-attempts/${attempt.id}/consent`, {
        method: 'POST',
      });
      setAttempt(a);
      const data = await api.request<{ questions: Question[] }>(
        `/psych-attempts/${a.id}/questions`,
      );
      setQuestions(data.questions);
    } catch (ex) {
      setMsg((ex as Error).message || 'ثبت رضایت ناموفق بود');
    } finally {
      setBusy(false);
    }
  }

  async function submitAll() {
    if (!attempt) return;
    if (Object.keys(answers).length < questions.length) {
      setMsg('به همه سؤال‌ها پاسخ دهید.');
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await api.request(`/psych-attempts/${attempt.id}/answers`, {
        method: 'POST',
        body: JSON.stringify({
          answers: Object.entries(answers).map(([question_id, option_index]) => ({
            question_id,
            option_index,
          })),
        }),
      });
      const result = await api.request<Attempt>(`/psych-attempts/${attempt.id}/submit`, {
        method: 'POST',
      });
      setAttempt(result);
      await load();
    } catch (ex) {
      setMsg((ex as Error).message || 'ثبت نتیجه ناموفق بود');
    } finally {
      setBusy(false);
    }
  }

  async function abandon() {
    if (!attempt) return;
    setBusy(true);
    try {
      await api.request(`/psych-attempts/${attempt.id}/abandon`, { method: 'POST' });
      setAttempt(null);
      setSelected(null);
      await load();
    } finally {
      setBusy(false);
    }
  }

  // ── نتیجه پس از نمره‌گذاری ──
  if (selected && attempt && ['scored', 'reviewed'].includes(attempt.status)) {
    return (
      <div style={{ padding: 16, textAlign: 'right' }}>
        <div style={card}>
          <h3>نتیجه آزمون «{selected.title}»</h3>
          <p>
            نمره خام: <b>{attempt.raw_score}</b>
          </p>
          <p>
            تفسیر (<b>{attempt.interpretation_title}</b>):
          </p>
          <p style={{ lineHeight: 2 }}>{attempt.interpretation_text}</p>
          <p style={{ fontSize: 12, color: '#6b7280' }}>
            این تفسیر به قاعده مصوب نسخه آزمون قابل ردیابی است
            {attempt.status === 'reviewed' ? ' و توسط ناظر علمی بازبینی شده است.' : '.'}
          </p>
          <button
            className="btn-primary"
            onClick={() => {
              setSelected(null);
              setAttempt(null);
            }}
          >
            بازگشت به فهرست آزمون‌ها
          </button>
        </div>
      </div>
    );
  }

  // ── صفحه اجرا (رضایت → سؤال‌ها) ──
  if (selected && attempt) {
    return (
      <div style={{ padding: 16, textAlign: 'right' }}>
        <div style={card}>
          <h3>{selected.title}</h3>
          <p style={{ fontSize: 13, color: '#374151' }}>{selected.purpose}</p>
          <p style={{ fontSize: 12, color: '#6b7280' }}>
            مقیاس: {selected.published_version?.scale_label ?? '—'} · نسخه:{' '}
            {selected.published_version?.version ?? '—'}
          </p>
        </div>

        {attempt.status === 'started' && (
          <div style={card}>
            <h4>رضایت اجرای آزمون</h4>
            <p style={{ fontSize: 13, lineHeight: 2 }}>
              برای ادامه، رضایت‌نامه اجرای آزمون روان‌شناسی را می‌پذیرم: نتیجه آزمون در
              پرونده من نگهداری می‌شود، تنها با نقش‌های مجاز (ناظر علمی) قابل مشاهده است و
              هر دسترسی به آن ثبت می‌شود.
            </p>
            <label style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '8px 0' }}>
              <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
              <span>متن فوق را مطالعه کردم و رضایت دارم.</span>
            </label>
            {msg && <div style={{ color: '#b91c1c', fontSize: 13 }}>{msg}</div>}
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn-primary" disabled={!agree || busy} onClick={grantConsentAndContinue}>
                {busy ? 'در حال ثبت…' : 'ثبت رضایت و شروع'}
              </button>
              <button className="btn-ghost" onClick={abandon} disabled={busy}>
                انصراف
              </button>
            </div>
          </div>
        )}

        {['consented', 'in_progress'].includes(attempt.status) && questions.length > 0 && (
          <div style={card}>
            {questions.map((q, qi) => (
              <div key={q.id} style={{ marginBottom: 14 }}>
                <p style={{ fontWeight: 600, margin: '0 0 6px' }}>
                  {qi + 1}. {q.text}
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {q.options.map((opt, oi) => (
                    <label key={oi} style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 }}>
                      <input
                        type="radio"
                        name={q.id}
                        checked={answers[q.id] === oi}
                        onChange={() => setAnswers((a) => ({ ...a, [q.id]: oi }))}
                      />
                      <span>{opt.label}</span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
            {msg && <div style={{ color: '#b91c1c', fontSize: 13 }}>{msg}</div>}
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn-primary" onClick={submitAll} disabled={busy}>
                {busy ? 'در حال ثبت…' : 'ثبت نهایی پاسخ‌ها'}
              </button>
              <button className="btn-ghost" onClick={abandon} disabled={busy}>
                رها کردن آزمون
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ── کاتالوگ + نتایج من ──
  return (
    <div style={{ padding: 16, textAlign: 'right' }}>
      <h3 style={{ margin: '4px 0 12px' }}>تست‌های روان‌شناسی</h3>
      {msg && <div style={{ color: '#b91c1c', fontSize: 13, marginBottom: 8 }}>{msg}</div>}
      {tests.map((t) => (
        <div key={t.id} style={card}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
            <div>
              <b>{t.title}</b>
              <p style={{ fontSize: 12, color: '#6b7280', margin: '4px 0' }}>{t.purpose}</p>
              <p style={{ fontSize: 12, color: '#6b7280', margin: 0 }}>
                {t.target_population}
                {t.age_min !== null || t.age_max !== null
                  ? ` · بازه سنی ${t.age_min ?? '۰'} تا ${t.age_max ?? '＋∞'}`
                  : ''}
                {t.scientific_doc ? ` · مستند: ${t.scientific_doc}` : ''}
              </p>
            </div>
            <button className="btn-primary" onClick={() => start(t)}>
              شروع آزمون
            </button>
          </div>
        </div>
      ))}
      {tests.length === 0 && (
        <p style={{ color: '#6b7280', fontSize: 13 }}>هنوز آزمونی منتشر نشده است.</p>
      )}

      <h3 style={{ margin: '18px 0 10px' }}>نتایج من</h3>
      {results.map((r) => (
        <div key={r.id} style={card}>
          <b>{STATUS_FA[r.status] ?? r.status}</b>
          {r.interpretation_title && (
            <p style={{ fontSize: 13, margin: '4px 0' }}>
              {r.interpretation_title} — نمره {r.raw_score}
            </p>
          )}
          {r.interpretation_text && (
            <p style={{ fontSize: 12, color: '#374151', margin: 0, lineHeight: 1.9 }}>
              {r.interpretation_text}
            </p>
          )}
        </div>
      ))}
      {results.length === 0 && (
        <p style={{ color: '#6b7280', fontSize: 13 }}>نتیجه‌ای ثبت نشده است.</p>
      )}
    </div>
  );
}
