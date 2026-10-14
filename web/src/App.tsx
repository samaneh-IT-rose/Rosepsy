import { useState } from 'react';
import { useAuth } from './lib/auth';
import Login from './pages/Login';
import Home from './pages/Home';
import Booking from './pages/Booking';

export default function App() {
  const { signedIn, loading } = useAuth();
  const [tab, setTab] = useState<'home' | 'booking'>('home');
  if (loading) return <div style={{ padding: 24 }}>در حال بارگذاری…</div>;
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
