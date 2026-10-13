import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth';

type Appointment = { id: string; start_at: string; end_at: string; status: string };
type Notification = { id: string; title: string; body: string; read: boolean; created_at: string };

export default function Home() {
  const { signOut } = useAuth();
  const qc = useQueryClient();
  const appts = useQuery({ queryKey: ['appointments'], queryFn: api.myAppointments });
  const notifs = useQuery({ queryKey: ['notifications'], queryFn: api.notifications });

  const handleSignOut = () => {
    signOut();
    qc.clear();
  };

  return (
    <div className="container">
      <h1>نوبت‌های من</h1>
      {appts.isLoading && <div>در حال بارگذاری…</div>}
      {appts.error && <div className="error">خطا در دریافت نوبت‌ها</div>}
      {appts.data && appts.data.length === 0 && <div>هنوز نوبتی ندارید</div>}
      {appts.data?.map((a) => (
        <li key={a.id}>
          {a.start_at.replace('T', ' ')}
          <span className="badge"> {a.status} </span>
        </li>
      ))}

      <h1 style={{ marginTop: 32 }}>اعلان‌ها</h1>
      {notifs.isLoading && <div>در حال بارگذاری…</div>}
      {notifs.data?.map((n) => (
        <li key={n.id}>
          <b>{n.title}</b>
          <div>{n.body}</div>
          {!n.read && <span className="badge">جدید</span>}
        </li>
      ))}

      <button onClick={handleSignOut} style={{ marginTop: 24 }}>
        خروج
      </button>
    </div>
  );
}