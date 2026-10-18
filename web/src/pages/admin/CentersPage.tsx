import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  createCenter,
  createCenterGroup,
  exportCentersUrl,
  getCenterDetail,
  getCenterGroups,
  getCenters,
  getProvinces,
  type CenterRow,
} from '../../lib/admin';
import { Modal, CenterDetailBlock, Paged } from './ui';

/** مراکز و کلینیک‌ها — doc s.6: groups block, regional filters, 5-column table,
 * Excel export (all filtered rows), centerDetail view. */
export default function CentersPage() {
  const [provinces, setProvinces] = useState<{ code: number; name: string }[]>([]);
  const [groups, setGroups] = useState<{ id: string; name: string }[]>([]);
  const [province, setProvince] = useState(0);
  const [city, setCity] = useState('');
  const [activation, setActivation] = useState('all');
  const [page, setPage] = useState(0);
  const [length, setLength] = useState(10);
  const [data, setData] = useState<{
    records_total: number;
    records_filtered: number;
    rows: CenterRow[];
  } | null>(null);
  const [detail, setDetail] = useState<(CenterRow & { clinic_name: string | null }) | null>(null);
  const [creating, setCreating] = useState(false);
  const [grouping, setGrouping] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getProvinces().then(setProvinces).catch(() => {});
    reloadGroups();
  }, []);

  function reloadGroups() {
    getCenterGroups().then(setGroups).catch(() => {});
  }

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (province) params.set('province', String(province));
    if (city) params.set('city', city);
    if (activation !== 'all') params.set('activation', activation);
    params.set('start', String(page * (length === -1 ? 0 : length)));
    params.set('length', String(length));
    try {
      setData(await getCenters(`?${params.toString()}`));
      setErr(null);
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }, [province, city, activation, page, length]);

  useEffect(() => {
    load();
  }, [load]);

  async function exportCsv() {
    const params = new URLSearchParams();
    if (province) params.set('province', String(province));
    if (city) params.set('city', city);
    if (activation !== 'all') params.set('activation', activation);
    const { getBlob } = await import('../../lib/admin');
    const blob = await getBlob(`${exportCentersUrl(`?${params.toString()}`)}`);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'centers.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  const rows = data?.rows ?? [];

  return (
    <div className="admin-page">
      <h2 className="admin-page-title">مراکز و کلینیک‌ها</h2>

      <div className="admin-card">
        <h3 className="admin-card-title">گروه‌بندی کلینیک‌ها</h3>
        <div className="admin-chip-row" style={{ alignItems: 'center' }}>
          {groups.map((g) => (
            <span key={g.id} className="admin-chip static">
              {g.name}
            </span>
          ))}
          <button className="btn-mini" onClick={() => setGrouping(true)}>
            + گروه جدید
          </button>
          <button className="btn-mini" onClick={() => setCreating(true)}>
            + ایجاد کلینیک
          </button>
        </div>
      </div>

      <div className="admin-card">
        <div className="admin-filter-row">
          <label className="admin-field">
            <span>استان</span>
            <select
              className="admin-select"
              value={province}
              onChange={(e) => {
                setPage(0);
                setProvince(Number(e.target.value));
              }}
            >
              <option value={0}>کل کشور</option>
              {provinces
                .filter((p) => p.code !== 0)
                .map((p) => (
                  <option key={p.code} value={p.code}>
                    {p.name}
                  </option>
                ))}
            </select>
          </label>
          <label className="admin-field">
            <span>شهرستان</span>
            <input
              value={city}
              onChange={(e) => {
                setPage(0);
                setCity(e.target.value);
              }}
              placeholder="بخشی از نام شهر…"
            />
          </label>
          <label className="admin-field">
            <span>وضعیت</span>
            <select
              className="admin-select"
              value={activation}
              onChange={(e) => {
                setPage(0);
                setActivation(e.target.value);
              }}
            >
              <option value="all">همه</option>
              <option value="1">فعال</option>
              <option value="0">غیرفعال</option>
            </select>
          </label>
          <button className="btn-ghost self-end" onClick={exportCsv}>
            خروجی اکسل (CSV)
          </button>
        </div>
      </div>

      <div className="admin-card">
        <table className="admin-table">
          <thead>
            <tr>
              <th>نام کلینیک</th>
              <th>استان</th>
              <th>شهر</th>
              <th>وضعیت کلینیک</th>
              <th>جزئیات</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="admin-empty">
                  رکوردی یافت نشد
                </td>
              </tr>
            )}
            {rows.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>{c.province ?? '—'}</td>
                <td>{c.city ?? '—'}</td>
                <td>
                  <span className={`badge ${c.is_active ? 'badge-green' : 'badge-gray'}`}>
                    {c.is_active ? 'فعال' : 'غیرفعال'}
                  </span>
                </td>
                <td>
                  <button
                    className="btn-mini"
                    onClick={async () => setDetail(await getCenterDetail(c.id))}
                  >
                    👁 مشاهده
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && (
          <Paged
            page={page}
            length={length}
            filtered={data.records_filtered}
            onPage={setPage}
            onLength={(l) => {
              setPage(0);
              setLength(l);
            }}
          />
        )}
        {err && <div className="admin-error">{err}</div>}
      </div>

      {detail && (
        <Modal title="جزئیات مرکز" onClose={() => setDetail(null)}>
          <CenterDetailBlock center={detail} />
        </Modal>
      )}

      {grouping && (
        <Modal title="ایجاد گروه‌بندی کلینیک" onClose={() => setGrouping(false)}>
          <GroupForm
            onDone={() => {
              setGrouping(false);
              reloadGroups();
            }}
          />
        </Modal>
      )}

      {creating && (
        <Modal title="ایجاد کلینیک" onClose={() => setCreating(false)} wide>
          <CenterForm
            provinces={provinces}
            groups={groups}
            onDone={() => {
              setCreating(false);
              setPage(0);
              load();
            }}
          />
        </Modal>
      )}
    </div>
  );
}

function GroupForm({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await createCenterGroup({ name, description: desc || undefined });
      onDone();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="admin-grid-2">
      <label className="admin-field">
        <span>نام گروه</span>
        <input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />
      </label>
      <label className="admin-field">
        <span>توضیح (اختیاری)</span>
        <input value={desc} onChange={(e) => setDesc(e.target.value)} />
      </label>
      {err && <div className="admin-error">{err}</div>}
      <button className="btn-primary" disabled={busy}>
        {busy ? '…' : 'ایجاد گروه'}
      </button>
    </form>
  );
}

function CenterForm({
  provinces,
  groups,
  onDone,
}: {
  provinces: { code: number; name: string }[];
  groups: { id: string; name: string }[];
  onDone: () => void;
}) {
  const [name, setName] = useState('');
  const [provinceCode, setProvinceCode] = useState(8);
  const [city, setCity] = useState('');
  const [address, setAddress] = useState('');
  const [groupId, setGroupId] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await createCenter({
        name,
        province_code: provinceCode,
        city,
        address: address || undefined,
        group_id: groupId || undefined,
      });
      onDone();
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="admin-grid-2">
      <label className="admin-field">
        <span>نام کلینیک</span>
        <input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />
      </label>
      <label className="admin-field">
        <span>استان</span>
        <select
          className="admin-select"
          value={provinceCode}
          onChange={(e) => setProvinceCode(Number(e.target.value))}
        >
          {provinces
            .filter((p) => p.code !== 0)
            .map((p) => (
              <option key={p.code} value={p.code}>
                {p.name}
              </option>
            ))}
        </select>
      </label>
      <label className="admin-field">
        <span>شهرستان</span>
        <input value={city} onChange={(e) => setCity(e.target.value)} required minLength={2} />
      </label>
      <label className="admin-field">
        <span>گروه (اختیاری)</span>
        <select className="admin-select" value={groupId} onChange={(e) => setGroupId(e.target.value)}>
          <option value="">— بدون گروه —</option>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
      </label>
      <label className="admin-field span-2">
        <span>آدرس (اختیاری)</span>
        <input value={address} onChange={(e) => setAddress(e.target.value)} />
      </label>
      {err && <div className="admin-error">{err}</div>}
      <button className="btn-primary" disabled={busy}>
        {busy ? '…' : 'ایجاد کلینیک'}
      </button>
    </form>
  );
}
