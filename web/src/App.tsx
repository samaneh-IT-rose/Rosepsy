import { useAuth } from './lib/auth';
import Login from './pages/Login';
import Home from './pages/Home';

export default function App() {
  const { signedIn, loading } = useAuth();
  if (loading) return <div style={{ padding: 24 }}>در حال بارگذاری…</div>;
  return signedIn ? <Home /> : <Login />;
}