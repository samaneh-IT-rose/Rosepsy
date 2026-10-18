import { useEffect, useState, type ReactNode } from 'react';

/**
 * Minimal hash router (dependency-free, matches project conventions).
 * Route shape: #/admin/<page>?<query>
 */

export interface Route {
  page: string;
  params: URLSearchParams;
}

export function parseHash(): Route {
  const raw = window.location.hash.replace(/^#\/?/, '');
  const [pathPart, queryPart] = raw.split('?');
  return {
    page: pathPart.replace(/^admin\/?/, '') || 'dashboard',
    params: new URLSearchParams(queryPart || ''),
  };
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(parseHash());
  useEffect(() => {
    const onChange = () => setRoute(parseHash());
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}

export function navigate(page: string, params?: Record<string, string>) {
  const qs = params ? `?${new URLSearchParams(params).toString()}` : '';
  window.location.hash = `#/admin/${page}${qs}`;
}

export function Placeholder({ title }: { title: string }) {
  return (
    <div className="admin-page">
      <h2 className="admin-page-title">{title}</h2>
      <div className="admin-card" style={{ textAlign: 'center', padding: 48 }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>🗂️</div>
        <p style={{ color: '#6b7280', lineHeight: 2 }}>
          این مسیر در «سند ساختاریافته شناسایی صفحات» فقط به‌صورت آیتم منو آمده و
          مشخصات صفحه آن (فیلدها و ستون‌ها) در سند نیامده است؛ پس از تکمیل سند،
          همین‌جا پیاده‌سازی می‌شود.
        </p>
      </div>
    </div>
  );
}
