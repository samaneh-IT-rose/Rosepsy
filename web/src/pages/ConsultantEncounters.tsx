import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';

type Encounter = {
  id: string;
  record_id: string;
  start_at: string;
  end_at: string;
  status: string;
};

export default function ConsultantEncounters({
  onSelect,
}: {
  onSelect: (encounterId: string) => void;
}) {
  const q = useQuery({ queryKey: ['my-encounters'], queryFn: api.myEncounters });

  if (q.isLoading) return <div>در حال بارگذاری…</div>;
  if (q.error) return <div className="error">خطا: {(q.error as Error).message}</div>;

  const items = q.data ?? [];
  if (items.length === 0) return <div>هنوز جلسه‌ای ندارید</div>;

  return (
    <div>
      <h2>جلسات من</h2>
      <ul>
        {items.map((e) => (
          <li key={e.id}>
            <div>
              {e.start_at.replace('T', ' ')} — {e.status}
            </div>
            <button onClick={() => onSelect(e.id)}>پرونده مراجع</button>
          </li>
        ))}
      </ul>
    </div>
  );
}