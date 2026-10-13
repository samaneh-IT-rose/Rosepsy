import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';

type Record = {
  id: string;
  user_id: string;
  summary: string | null;
  risk_level: string;
};

export default function ConsultantRecord({ encounterId }: { encounterId: string }) {
  const q = useQuery({
    queryKey: ['encounter-record', encounterId],
    queryFn: () => api.encounterRecord(encounterId),
  });

  if (q.isLoading) return <div>در حال بارگذاری…</div>;
  if (q.error) return <div className="error">خطا: {(q.error as Error).message}</div>;

  const r = q.data;
  return (
    <div>
      <h2>پرونده مراجع</h2>
      <div>
        <b>خلاصه:</b> {r.summary || '—'}
      </div>
      <div>
        <b>سطح ریسک:</b> {r.risk_level}
      </div>
    </div>
  );
}