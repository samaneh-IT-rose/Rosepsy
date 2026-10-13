import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth';
import ConsultantEncounters from './ConsultantEncounters';
import ConsultantRecord from './ConsultantRecord';

type Appointment = { id: string; start_at: string; status: string };
type Notification = { id: string; title: string; body: string; read: boolean };

export default function Home() {
  const { signOut } = useAuth();
  const qc = useQueryClient();
  const [tab, setTab] = useState<'appointments' | 'notifications' | 'encounters'>(
    'appointments'
  );
  const [selectedEncounter, setSelectedEncounter] = useState<string | null>(null);

  const me = useQuery({ queryKey: ['me'], queryFn: api.me });
  const isConsultant = me.data?.roles?.includes('consultant') ?? false;

  const appts = useQuery({ queryKey: ['appointments'], queryFn: api.myAppointments });
  const notifs = useQuery({ queryKey: ['notifications'], queryFn: api.notifications });

  const handleSignOut = () => {
    signOut();
    qc.clear();
  };

  return (
    <div className="container">
      <h1>کلینیک رز</h1>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          style={{ width: 'auto', padding: '8px 16px' }}
          onClick={() => setTab('appointments')}
        >
          نوبت‌ها
        </button>
        <button
          style={{ width: 'auto', padding: '8px 16px' }}
          onClick={() => setTab('notifications')}
        >
          اعلان‌ها
        </button>
        {isConsultant && (
          <button
            style={{ width: 'auto', padding: '8px 16px' }}
            onClick={() => setTab('encounters')}
          >
            جلسات من
          </button>
        )}
        <button
          style={{ width: 'auto', padding: '8px 16px', background: '#888' }}
          onClick={handleSignOut}
        >
          خروج
        </button>
      </div>

      {tab === 'appointments' && (
        <>
          <h2>نوبت‌های من</h2>
          {appts.isLoading && <div>در حال بارگذاری…</div>}
          {appts.data && appts.data.length === 0 && <div>هنوز نوبتی ندارید</div>}
          {appts.data?.map((a) => (
            <li key={a.id}>
              {a.start_at.replace('T', ' ')}
              <span className="badge"> {a.status} </span>
            </li>
          ))}
        </>
      )}

      {tab === 'notifications' && (
        <>
          <h2>اعلان‌ها</h2>
          {notifs.isLoading && <div>در حال بارگذاری…</div>}
          {notifs.data?.map((n) => (
            <li key={n.id}>
              <b>{n.title}</b>
              <div>{n.body}</div>
              {!n.read && <span className="badge">جدید</span>}
            </li>
          ))}
        </>
      )}

      {tab === 'encounters' && isConsultant && (
        <>
          <h2>جلسات من (مشاور)</h2>
          {selectedEncounter ? (
            <>
              <button
                style={{ width: 'auto', padding: '8px 16px' }}
                onClick={() => setSelectedEncounter(null)}
              >
                بازگشت به جلسات
              </button>
              <ConsultantRecord encounterId={selectedEncounter} />
            </>
          ) : (
            <ConsultantEncounters onSelect={setSelectedEncounter} />
          )}
        </>
      )}
    </div>
  );
}