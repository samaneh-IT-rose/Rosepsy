import type { DashboardData } from '../../lib/admin';
import { useHashRoute, navigate } from './router';

export default function Dashboard({ data }: { data: DashboardData | null }) {
  const route = useHashRoute();
  if (!data) return <div className="admin-loading">در حال بارگذاری داشبورد…</div>;

  const stats = [
    { label: 'کاربران', value: data.stats.users, to: 'users' },
    { label: 'مراکز و کلینیک‌ها', value: data.stats.centers, to: 'centers' },
    { label: 'مشاوران', value: data.stats.consultants, to: null },
    { label: 'ارجاعات', value: data.stats.referrals, to: null },
  ];

  return (
    <div className="admin-page">
      <div className="admin-hero">
        <div>
          <h2>{data.identity.title}</h2>
          <span className="admin-hero-badge">{data.identity.badge}</span>
        </div>
      </div>

      <div className="admin-stat-grid">
        {stats.map((s) => (
          <button
            key={s.label}
            className="admin-stat"
            onClick={() => s.to && navigate(s.to)}
            style={{ cursor: s.to ? 'pointer' : 'default' }}
          >
            <div className="admin-stat-value">{s.value.toLocaleString('fa-IR')}</div>
            <div className="admin-stat-label">{s.label}</div>
          </button>
        ))}
      </div>

      <div className="admin-card">
        <h3 className="admin-card-title">میانبرهای دسکتاپ</h3>
        <div className="admin-chip-row">
          {data.shortcuts.map((sc) => (
            <a
              key={sc.path}
              className="admin-chip"
              href={`#/admin/${ROUTE_OF(sc.path)}`}
            >
              {sc.title}
            </a>
          ))}
        </div>
      </div>

      <div className="admin-card">
        <h3 className="admin-card-title">{data.user_section.title}</h3>
        <div className="admin-chip-row">
          {data.user_section.links.map((l) =>
            l.path.startsWith('http') ? (
              <a key={l.title} className="admin-chip" href={l.path} target="_blank" rel="noreferrer">
                {l.title} ↗
              </a>
            ) : (
              <a key={l.title} className="admin-chip" href={l.path === '/eventReserve' ? '#/' : '#'}>
                {l.title}
              </a>
            ),
          )}
        </div>
      </div>
    </div>
  );
}

/** Menu path → hash page key for implemented pages. */
function ROUTE_OF(path: string): string {
  const map: Record<string, string> = {
    '/system-settings': 'system-settings',
    '/admin-editusers': 'users',
    '/centers': 'centers',
    '/logs': 'logs',
    '/reports': 'reports',
  };
  return map[path] ?? path.replace(/^\//, '');
}
