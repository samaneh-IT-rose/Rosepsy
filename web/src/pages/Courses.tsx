import { useCallback, useEffect, useState } from 'react';
import { api } from '../lib/api';

type Course = {
  id: string;
  title: string;
  slug: string;
  summary: string | null;
  instructor_name: string | null;
  is_free: boolean;
  price: number;
};

type MyCourse = {
  enrollment_id: string;
  course_id: string;
  title: string | null;
  slug: string | null;
  status: string;
  progress: { completed_lessons: number; total_lessons: number };
  certificates: string[];
};

const STATUS_FA: Record<string, string> = {
  active: 'فعال',
  pending_payment: 'در انتظار پرداخت',
  completed: 'تکمیل‌شده',
  expired: 'منقضی',
  revoked: 'لغو‌شده',
};

const card: React.CSSProperties = {
  border: '1px solid #e5e7eb',
  borderRadius: 12,
  padding: '14px 16px',
  background: '#fff',
  textAlign: 'right',
};
const btn: React.CSSProperties = {
  padding: '6px 14px',
  borderRadius: 8,
  border: '1px solid #94365e',
  background: '#94365e',
  color: '#fff',
  cursor: 'pointer',
};

export default function Courses() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [mine, setMine] = useState<MyCourse[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setCourses(await api.request<Course[]>('/public/courses'));
      setMine(await api.request<MyCourse[]>('/my-courses'));
    } catch {
      /* unauthenticated parts load anyway */
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const enroll = async (courseId: string) => {
    setMsg(null);
    try {
      const res = await api.request<{
        status: string;
        order_id?: string;
        already_enrolled: boolean;
      }>(`/courses/${courseId}/enrollments`, { method: 'POST', body: '{}' });
      if (res.status === 'pending_payment' && res.order_id) {
        // pay via gateway mock flow
        const pay = await api.request<{ gateway_ref: string }>('/payments/start', {
          method: 'POST',
          body: JSON.stringify({ order_id: res.order_id }),
        });
        await api.request<{
          order_status: string;
          invoice_id: string | null;
        }>('/payments/callback', {
          method: 'POST',
          body: JSON.stringify({ gateway_ref: pay.gateway_ref, result: 'success' }),
        });
        setMsg('پرداخت انجام و دسترسی دوره فعال شد ✅');
      } else if (res.already_enrolled) {
        setMsg('قبلاً در این دوره ثبت‌نام کرده‌اید.');
      } else {
        setMsg('ثبت‌نام رایگان انجام شد ✅');
      }
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'خطا در ثبت‌نام');
    }
  };

  return (
    <div style={{ padding: 16, display: 'grid', gap: 16 }}>
      <h2 style={{ margin: 0 }}>دوره‌های آموزشی</h2>
      {msg && (
        <div style={{ background: '#eaf7f5', padding: '8px 12px', borderRadius: 8 }}>{msg}</div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(260px,1fr))', gap: 12 }}>
        {courses.map((c) => (
          <div key={c.slug} style={card}>
            <strong>{c.title}</strong>
            <p style={{ color: '#607385', fontSize: 12 }}>{c.summary}</p>
            <div style={{ fontSize: 12, marginBottom: 8 }}>
              مدرس: {c.instructor_name || '—'} ·{' '}
              {c.is_free ? 'رایگان' : `${c.price.toLocaleString('fa-IR')} ریال`}
            </div>
            <button style={btn} onClick={() => void enroll(c.id)}>
              ثبت‌نام
            </button>
          </div>
        ))}
        {courses.length === 0 && <p style={{ color: '#607385' }}>دوره‌ای منتشر نشده است.</p>}
      </div>

      <h3 style={{ margin: '8px 0 0' }}>دوره‌های من</h3>
      <div style={{ display: 'grid', gap: 8 }}>
        {mine.map((m) => (
          <div key={m.enrollment_id} style={card}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <strong>{m.title}</strong>
              <span style={{ fontSize: 12, color: '#94365e' }}>
                {STATUS_FA[m.status] || m.status}
              </span>
            </div>
            <div style={{ fontSize: 12, color: '#607385' }}>
              پیشرفت: {m.progress.completed_lessons} از {m.progress.total_lessons} درس
              {m.certificates.length > 0 && ` · گواهی: ${m.certificates.join('، ')}`}
            </div>
          </div>
        ))}
        {mine.length === 0 && <p style={{ color: '#607385' }}>هنوز ثبت‌نامی ندارید.</p>}
      </div>
    </div>
  );
}
