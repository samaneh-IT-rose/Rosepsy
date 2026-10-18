import { useEffect, useState } from 'react';
import { useAuth } from './lib/auth';
import Login from './pages/Login';
import Home from './pages/Home';
import Booking from './pages/Booking';
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
  const [tab, setTab] = useState<'home' | 'booking'>('home');
  if (!signedIn) return <Login />;
  return (
    <div>
      <div style={{ display: 'flex', gap: 8, padding: '12px 24px', borderBottom: '1px solid #e5e7eb' }}>
        <button onClick={() => setTab('home')}>خانه</button>
        <button onClick={() => setTab('booking')}>رزرو نوبت</button>
      </div>
      {tab === 'home' ? <Home /> : <Booking />}
    </div>
  );
}
