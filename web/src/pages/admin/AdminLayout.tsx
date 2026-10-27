import { useEffect, useState } from 'react';
import { getDashboard, type DashboardData } from '../../lib/admin';
import { useAuth } from '../../lib/auth';
import { useHashRoute, navigate } from './router';
import Dashboard from './Dashboard';
import UsersPage from './UsersPage';
import UserProfilePage from './UserProfilePage';
import CentersPage from './CentersPage';
import ReportsPage from './ReportsPage';
import LogsPage from './LogsPage';
import WalletsAdmin from './WalletsAdmin';
import DiscountsAdmin from './DiscountsAdmin';
import RefundsAdmin from './RefundsAdmin';
import AccountingAdmin from './AccountingAdmin';
import PsychTestsAdmin from './PsychTestsAdmin';
import ContentsAdmin from './ContentsAdmin';
import CoursesAdmin from './CoursesAdmin';
import { Placeholder } from './router';

/** Map a سند menu path → implemented page key. */
const PATH_TO_PAGE: Record<string, string> = {
  '/admin-editusers': 'users',
  '/payments': 'wallets',
  '/wallets': 'wallets',
  '/discounts': 'discounts',
  '/refunds': 'refunds',
  '/accounting': 'accounting',
  '/psych-tests': 'psych-tests',
  '/contents': 'contents',
  '/courses': 'courses',
  '/profile': 'user-profile',
  '/centers': 'centers',
  '/reports': 'reports',
  '/logs': 'logs',
  '/invitepersons': 'reports',
  '/referrs-requests': 'reports',
  '/event-report': 'reports',
  '/undone-event-report': 'reports',
  '/event-group-report': 'reports',
  '/undone-event-group-report': 'reports',
  '/admin-referrs-requests': 'reports',
};

export default function AdminLayout() {
  const { signOut } = useAuth();
  const route = useHashRoute();
  const [dash, setDash] = useState<DashboardData | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    getDashboard().then(setDash).catch(() => setDash(null));
  }, []);

  const menus = dash?.menus ?? [];
  const currentPath = `/${route.page}`;

  function renderPage() {
    switch (route.page) {
      case 'dashboard':
        return <Dashboard data={dash} />;
      case 'users':
        return <UsersPage />;
      case 'user-profile':
        return <UserProfilePage userId={route.params.get('user')} />;
      case 'centers':
        return <CentersPage />;
      case 'reports':
        return <ReportsPage report={route.params.get('report') ?? undefined} />;
      case 'logs':
        return <LogsPage />;
      case 'wallets':
        return <WalletsAdmin />;
      case 'discounts':
        return <DiscountsAdmin />;
      case 'refunds':
        return <RefundsAdmin />;
      case 'accounting':
        return <AccountingAdmin />;
      case 'psych-tests':
        return <PsychTestsAdmin />;
      case 'contents':
        return <ContentsAdmin />;
      case 'courses':
        return <CoursesAdmin />;
      default:
        return <Placeholder title={DOC_TITLE(route.page)} />;
    }
  }

  return (
    <div className="admin-shell">
      <aside className={`admin-sidebar ${menuOpen ? 'open' : ''}`}>
        <div className="admin-brand">
          <div className="admin-brand-badge">{dash?.identity.badge ?? 'ادمین'}</div>
          <span>راه زندگی رز سفید</span>
        </div>
        <nav className="admin-menu">
          {menus.map((m) => {
            const target = PATH_TO_PAGE[m.path];
            const active =
              (target && currentPath === m.path) ||
              (!target && window.location.hash === `#${m.path}`);
            return (
              <a
                key={m.path}
                className={`admin-menu-item ${active ? 'active' : ''}`}
                href={target ? `#/admin/${PATH_PAGE[target]}` : `#${m.path}`}
                title={`${m.path}?access=admin`}
              >
                <span className="admin-menu-icn" aria-hidden>
                  {ICON_EMOJI[m.icon] ?? '▫'}
                </span>
                <span>{m.title}</span>
                {!target && <span className="admin-menu-soon">سند کامل نیست</span>}
              </a>
            );
          })}
        </nav>
      </aside>

      <div className="admin-main">
        <header className="admin-topbar">
          <button className="admin-burger" onClick={() => setMenuOpen((v) => !v)}>
            ☰
          </button>
          <div className="admin-topbar-title">{dash?.identity.title ?? 'پنل مدیریت'}</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn-ghost" onClick={() => navigate('dashboard')}>
              داشبورد
            </button>
            <button className="btn-ghost" onClick={signOut}>
              خروج
            </button>
          </div>
        </header>
        <main className="admin-content" onClick={() => setMenuOpen(false)}>
          {renderPage()}
        </main>
      </div>
    </div>
  );
}

const PATH_PAGE: Record<string, string> = {
  wallets: 'wallets',
  discounts: 'discounts',
  refunds: 'refunds',
  accounting: 'accounting',
  'psych-tests': 'psych-tests',
  contents: 'contents',
  courses: 'courses',
  users: 'users',
  'user-profile': 'user-profile',
  centers: 'centers',
  reports: 'reports',
  logs: 'logs',
};

function DOC_TITLE(page: string): string {
  const found = (window as unknown as { __adminMenus?: { path: string; title: string }[] })
    .__adminMenus?.find((m) => m.path === `/${page}`);
  return found?.title ?? page;
}

/** Small visual substitutes until the real icon-font assets ship (UI-only). */
const ICON_EMOJI: Record<string, string> = {
  'dashboardlist-gear-2': '⚙️',
  'dashboardlist-management-setting': '🧮',
  'dashboardlist-group': '👥',
  'folder-net': '🌐',
  'folder-docs': '📄',
  'folder-pen': '📝',
  'folder-open': '📂',
  'dashboardlist-user-review': '🔎',
  'folder-close': '📁',
  'folder-favs': '⭐',
  'file-js': '🗒️',
  'dashboardlist-emergency': '🚨',
  'dashboardlist-daily-report': '💰',
  'dashboardlist-recipient-report': '📊',
  'dashboardlist-consultant-tax': '🧾',
  'dashboardlist-report': '📈',
  'dashboardlist-pie-chart': '🥧',
  'dashboardlist-bi-critical-cases': '📉',
  'dashboardlist-notification': '✉️',
  'dashboardlist-admin-messages': '💬',
  'dashboardlist-special-occasions': '📅',
  'file-log': '🧭',
  'file-chm': '🎫',
  'dashboardlist-help': '❓',
  'dashboardlist-wallet': '👛',
  'dashboardlist-discount': '🏷️',
  'dashboardlist-refund': '↩️',
  'dashboardlist-accounting': '📊',
  'dashboardlist-psych': '🧠',
  'dashboardlist-contents': '📰',
  'dashboardlist-courses': '🎓',
};
