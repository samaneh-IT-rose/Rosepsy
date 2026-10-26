import { useEffect, useState } from 'react';
import { useAuth } from './lib/auth';
import Login from './pages/Login';
import Home from './pages/Home';
import Booking from './pages/Booking';
import Courses from './pages/Courses';
import Contents from './pages/Contents';
import WalletPage from './pages/Wallet';
import PsychTests from './pages/PsychTests';
import AdminLayout from './pages/admin/AdminLayout';

function isAdminHash() {
  return window.location.hash.startsWith('#/admin');
}

export default function App() {
  const { signedIn, loading } = useAuth();
  const [adminMode, setAdminMode] = useState(isAdminHash());

  useEffect(() => {
    const onChange = () => setAdminMode(isAdminHash());
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  if (loading) return <div style={{ padding: 24 }}>در حال بارگذاری…</div>;

  if (signedIn && adminMode) return <AdminLayout />;

  return <UserApp />;
}

function UserApp() {
  const { signedIn } = useAuth();
  const [tab, setTab] = useState<'home' | 'booking' | 'courses' | 'contents' | 'wallet' | 'tests'>('home');
  if (!signedIn) return <Login />;
  return (
    <div>
      <div style={{ display: 'flex', gap: 8, padding: '12px 24px', borderBottom: '1px solid #e5e7eb', flexWrap: 'wrap' }}>
        <button onClick={() => setTab('home')}>خانه</button>
        <button onClick={() => setTab('booking')}>رزرو نوبت</button>
        <button onClick={() => setTab('courses')}>دوره‌ها</button>
        <button onClick={() => setTab('contents')}>محتوا</button>
        <button onClick={() => setTab('wallet')}>کیف پول</button>
        <button onClick={() => setTab('tests')}>تست روان‌شناسی</button>
      </div>
      {tab === 'home' && <Home />}
      {tab === 'booking' && <Booking />}
      {tab === 'courses' && <Courses />}
      {tab === 'contents' && <Contents />}
      {tab === 'wallet' && <WalletPage />}
      {tab === 'tests' && <PsychTests />}
    </div>
  );
}
