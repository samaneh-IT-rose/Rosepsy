import { useEffect, useState } from 'react';
import { api } from '../lib/api';

type ContentItem = {
  type: string;
  title: string;
  slug: string;
  summary: string | null;
  published_at: string | null;
  topics: string[];
};

type ContentDetail = ContentItem & { body: string | null; seo_title: string | null };

const TYPE_FA: Record<string, string> = {
  article: 'مقاله',
  news: 'خبر',
  podcast: 'پادکست',
  video: 'ویدئو',
};

const card: React.CSSProperties = {
  border: '1px solid #e5e7eb',
  borderRadius: 12,
  padding: '14px 16px',
  background: '#fff',
  textAlign: 'right',
  cursor: 'pointer',
};

export default function Contents() {
  const [items, setItems] = useState<ContentItem[]>([]);
  const [type, setType] = useState<string>('');
  const [q, setQ] = useState('');
  const [detail, setDetail] = useState<ContentDetail | null>(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (type) params.set('type', type);
    if (q.trim()) params.set('q', q.trim());
    api
      .request<ContentItem[]>(`/public/contents?${params.toString()}`)
      .then(setItems)
      .catch(() => setItems([]));
  }, [type, q]);

  const open = async (slug: string) => {
    try {
      setDetail(await api.request<ContentDetail>(`/public/contents/${slug}`));
    } catch {
      setDetail(null);
    }
  };

  if (detail) {
    return (
      <div style={{ padding: 16, maxWidth: 760, margin: 'auto', textAlign: 'right' }}>
        <button
          onClick={() => setDetail(null)}
          style={{
            marginBottom: 12,
            padding: '6px 12px',
            borderRadius: 8,
            border: '1px solid #e5e7eb',
            background: '#fff',
            cursor: 'pointer',
          }}
        >
          ← بازگشت به فهرست
        </button>
        <h2 style={{ margin: '0 0 4px' }}>{detail.title}</h2>
        <div style={{ color: '#607385', fontSize: 12, marginBottom: 12 }}>
          {TYPE_FA[detail.type] || detail.type}
          {detail.topics.length > 0 && ` · ${detail.topics.join('، ')}`}
        </div>
        <p style={{ lineHeight: 2.1, whiteSpace: 'pre-wrap' }}>{detail.body}</p>
      </div>
    );
  }

  return (
    <div style={{ padding: 16, display: 'grid', gap: 12, textAlign: 'right' }}>
      <h2 style={{ margin: 0 }}>محتوای عمومی</h2>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        {['', 'article', 'news', 'podcast', 'video'].map((t) => (
          <button
            key={t || 'all'}
            onClick={() => setType(t)}
            style={{
              padding: '5px 12px',
              borderRadius: 999,
              border: '1px solid ' + (type === t ? '#94365e' : '#e5e7eb'),
              background: type === t ? '#faedf3' : '#fff',
              cursor: 'pointer',
              fontSize: 12,
            }}
          >
            {t === '' ? 'همه' : TYPE_FA[t]}
          </button>
        ))}
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="جست‌وجو…"
          style={{
            padding: '6px 12px',
            borderRadius: 8,
            border: '1px solid #e5e7eb',
            flex: 1,
            minWidth: 160,
          }}
        />
      </div>
      <div style={{ display: 'grid', gap: 8 }}>
        {items.map((c) => (
          <div key={c.slug} style={card} onClick={() => void open(c.slug)}>
            <strong>{c.title}</strong>
            <div style={{ fontSize: 12, color: '#607385' }}>
              {TYPE_FA[c.type] || c.type}
              {c.summary ? ` — ${c.summary}` : ''}
            </div>
          </div>
        ))}
        {items.length === 0 && <p style={{ color: '#607385' }}>محتوایی یافت نشد.</p>}
      </div>
    </div>
  );
}
