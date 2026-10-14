import { useEffect, useState, type CSSProperties } from 'react';
import { api, getToken } from '../lib/api';

const box: CSSProperties = { padding: 24, maxWidth: 720 };
const card: CSSProperties = {
  border: '1px solid #e5e7eb', borderRadius: 12, padding: 16, margin: '12px 0',
};
const sel: CSSProperties = { padding: 8, margin: '4px 0', width: '100%' };
const btn: CSSProperties = {
  padding: '8px 16px', margin: 4, borderRadius: 8,
  border: '1px solid #94365e', background: '#94365e', color: '#fff', cursor: 'pointer',
};
const btn2: CSSProperties = {
  padding: '6px 12px', margin: 3, borderRadius: 8, border: '1px solid #94365e',
  background: '#faedf3', color: '#6f284b', cursor: 'pointer',
};

function slotStart(s: any): string | null {
  if (typeof s === 'string') return s;
  if (s && typeof s === 'object') return s.start_at || s.starts_at || s.start || null;
  return null;
}

function findUuidByKey(o: any, needle: string): string | null {
  if (Array.isArray(o)) {
    for (const v of o) { const r = findUuidByKey(v, needle); if (r) return r; }
    return null;
  }
  if (o && typeof o === 'object') {
    for (const [k, v] of Object.entries(o)) {
      if (k.toLowerCase().includes(needle) && typeof v === 'string' && v.length === 36) return v;
      const r = findUuidByKey(v, needle);
      if (r) return r;
    }
  }
  return null;
}

function findRef(o: any): string | null {
  if (Array.isArray(o)) {
    for (const v of o) { const r = findRef(v); if (r) return r; }
    return null;
  }
  if (o && typeof o === 'object') {
    for (const [k, v] of Object.entries(o)) {
      if (typeof v === 'string' && /ref/i.test(k) && v.length >= 4 && v.length <= 64) return v;
      const r = findRef(v);
      if (r) return r;
    }
  }
  return null;
}

export default function Booking() {
  const [services, setServices] = useState<any[]>([]);
  const [consultants, setConsultants] = useState<any[]>([]);
  const [serviceId, setServiceId] = useState('');
  const [consultantId, setConsultantId] = useState('');
  const [dates, setDates] = useState<Record<string, any>>({});
  const [slot, setSlot] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [stage, setStage] = useState('');
  const [order, setOrder] = useState<any>(null);
  const [orderStatus, setOrderStatus] = useState('');
  const [invoice, setInvoice] = useState<any>(null);

  useEffect(() => {
    api.listServices().then(setServices).catch((e) => setError(e.message));
    api.listConsultants().then(setConsultants).catch(() => {});
  }, []);

  useEffect(() => {
    if (!serviceId || !consultantId) return;
    setSlot(null); setDates({}); setError('');
    api.availability(consultantId, serviceId)
      .then((a: any) => setDates(a?.dates || {}))
      .catch((e) => setError(e.message));
  }, [serviceId, consultantId]);

  async function pollOrder(orderId: string): Promise<any> {
    for (let i = 0; i < 3; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      const o: any = await api.getOrder(orderId);
      setOrderStatus(o.status || '');
      if (o.status === 'paid') return o;
      if (o.status === 'failed') return o;
    }
    return null;
  }

  async function finishPaid(o: any) {
    const iid = findUuidByKey(o, 'invoice');
    if (iid) {
      try { setInvoice(await api.getInvoice(iid)); } catch { setInvoice({ id: iid }); }
    }
  }

  async function book() {
    if (!slot) return;
    setBusy(true); setError(''); setStage('نگه‌داشتن زمان…'); setInvoice(null); setOrder(null);
    try {
      const hold = await api.createHold({ consultant_id: consultantId, service_id: serviceId, start_at: slot });
      setStage('ثبت نوبت…');
      const appt = await api.createAppointment(hold.id);
      setStage('ساخت سفارش…');
      const ord = await api.createOrder(appt.id, crypto.randomUUID());
      setOrder(ord); setOrderStatus(ord.status || '');
      setStage('شروع پرداخت…');
      const ps = await api.startPayment(ord.id);
      setStage('در انتظار تأیید پرداخت…');
      const paid = await pollOrder(ord.id);
      if (paid) { await finishPaid(paid); setStage('پرداخت موفق'); }
      else {
        setStage('پرداخت تأیید نشد — درگاه آزمایشی');
        try { const cb: any = await api.paymentCallback(findRef(ps) || ord.id); const iid: string | null = cb?.invoice_id || null; const o2 = await pollOrder(ord.id);
          if (o2) { if (iid) { try { const inv: any = await api.getInvoice(iid); console.log('INVOICE', inv); setInvoice(inv); } catch { setInvoice({ id: iid }); } } else { await finishPaid(o2); } setStage('پرداخت موفق'); } else setError('پرداخت تأیید نشد');
        } catch (e: any) { setError('شبیه‌سازی درگاه: ' + e.message); }
      }
    } catch (e: any) {
      setError(e.message || 'خطا');
    } finally { setBusy(false); setStage(''); }
  }

  async function downloadPdf() {
    if (!invoice?.id) return;
    const res = await fetch(api.invoicePdfUrl(invoice.id), {
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'invoice.pdf'; a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div style={box}>
      <h2>رزرو نوبت</h2>
      {error && <div style={{ color: '#c53939', margin: '8px 0' }}>خطا: {error}</div>}

      <div style={card}>
        <div>خدمت:</div>
        <select style={sel} value={serviceId} onChange={(e) => setServiceId(e.target.value)}>
          <option value="">— انتخاب کنید —</option>
          {services.map((s) => (
            <option key={s.id} value={s.id}>{s.name} ({s.duration_minutes} دقیقه)</option>
          ))}
        </select>
        <div>مشاور:</div>
        <select style={sel} value={consultantId} onChange={(e) => setConsultantId(e.target.value)}>
          <option value="">— انتخاب کنید —</option>
          {consultants.map((c) => (
            <option key={c.id} value={c.id}>{c.display_name}</option>
          ))}
        </select>
      </div>

      {loadingDates(dates) && <div>در حال بارگذاری زمان‌ها…</div>}
      {Object.entries(dates).map(([d, slots]) => (
        <div style={card} key={d}>
          <strong>{d}</strong>
          <div>
            {(Array.isArray(slots) ? slots : []).map((s: any, i: number) => {
              const st = slotStart(s);
              if (!st) return null;
              return (
                <button key={i} style={st === slot ? btn : btn2}
                  onClick={() => setSlot(st)}>
                  {st.slice(11, 16)}
                </button>
              );
            })}
          </div>
        </div>
      ))}

      {slot && !order && (
        <button style={btn} disabled={busy} onClick={book}>
          {busy ? 'در حال انجام…' : 'ثبت رزرو و پرداخت'}
        </button>
      )}

      {stage && <div style={{ margin: '12px 0' }}>{stage}</div>}

      {order && (
        <div style={card}>
          <div>وضعیت سفارش: {orderStatus || '…'}</div>
          {invoice && (
            <div style={{ marginTop: 8 }}>
              <div>فاکتور: {invoice.number || invoice.invoice_number || invoice.id}</div>
              <div>مبلغ: {invoice.total_amount ?? invoice.amount ?? '—'}</div>
              <button style={btn2} onClick={downloadPdf}>دانلود PDF فاکتور</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function loadingDates(dates: Record<string, any>) {
  return false;
}


