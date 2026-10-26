// Admin panel API client (B42) — mirrors backend/app/api/admin.py endpoints.
import { api } from './api';

export interface Envelope<T> {
  data: T;
  errors: { code: string; message: string }[] | null;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api/v1'}${path}`, {
    headers: api_token(),
  });
  const json = (await res.json()) as Envelope<T>;
  if (res.status >= 400 || json.errors) {
    throw new Error(json.errors?.[0]?.message || `HTTP ${res.status}`);
  }
  return json.data;
}

export async function getBlob(path: string): Promise<Blob> {
  const res = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api/v1'}${path}`, {
    headers: api_token(),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.blob();
}

function api_token(): Record<string, string> {
  const t = localStorage.getItem('auth_token');
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api/v1'}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...api_token() },
    body: JSON.stringify(body),
  });
  const json = (await res.json()) as Envelope<T>;
  if (res.status >= 400 || json.errors) {
    throw new Error(json.errors?.[0]?.message || `HTTP ${res.status}`);
  }
  return json.data;
}

async function post<T>(path: string, body?: unknown, idempotencyKey?: string): Promise<T> {
  const res = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api/v1'}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
      ...api_token(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const json = (await res.json()) as Envelope<T>;
  if (res.status >= 400 || json.errors) {
    throw new Error(json.errors?.[0]?.message || `HTTP ${res.status}`);
  }
  return json.data;
}

// ───────── dashboard & reference ─────────
export const getDashboard = () => get<DashboardData>('/admin/dashboard');
export const getProvinces = () => get<{ code: number; name: string }[]>('/admin/provinces');
export const getCities = (provinceCode: number) =>
  get<{ id: string; name: string }[]>(`/admin/cities?province_code=${provinceCode}`);

export interface DashboardData {
  identity: { title: string; badge: string; theme: string };
  shortcuts: MenuItem[];
  menus: MenuItem[];
  user_section: {
    title: string;
    badge: string;
    theme: string;
    links: { title: string; path: string; icon: string }[];
  };
  stats: { users: number; centers: number; consultants: number; referrals: number };
}

export interface MenuItem {
  title: string;
  path: string;
  icon: string;
}

// ───────── users (doc s.4) ─────────
export interface UserRow {
  id: string;
  code: number | null;
  username: string | null;
  full_name: string | null;
  father_name: string | null;
  gender_fa: string | null;
  mobile: string;
  province_fa: string | null;
  province_code: number | null;
  education: string | null;
  birth_date: string | null;
  registered_at: string;
  last_login_at: string | null;
  details: {
    username: string | null;
    email: string | null;
    address: string | null;
    postal_code: string | null;
    registration_source: string | null;
  };
}

export const getUsers = (params: string) =>
  get<{
    records_total: number;
    records_filtered: number;
    offset: number;
    columns: string[];
    rows: UserRow[];
  }>(`/admin/users${params}`);

export const editUser = (id: string, body: Record<string, unknown>) =>
  patch<{ id: string; changed: string[] }>(`/admin/users/${id}`, body);

export const switchSession = (id: string) =>
  post<{ access_token: string; user: { id: string; phone: string } }>(
    `/admin/users/${id}/switch-session`,
  );

// ───────── user profile (doc s.5) ─────────
export interface UserProfile {
  personal: Record<string, string | number | null>;
  services: {
    columns: string[];
    rows: {
      id: string;
      code: number;
      referral_code: number | null;
      service: string | null;
      contract: string | null;
      user_tariff: number | null;
      acute_fa: string | null;
      consultant: string | null;
      branch: string | null;
      status_fa: string | null;
      start_at: string;
      end_at: string;
      details_options: { value: string; title: string }[];
    }[];
  };
}

export const getUserProfile = (id: string) => get<UserProfile>(`/admin/users/${id}`);

export interface EventDetails {
  appointment_code: number;
  kind: string;
  event?: Record<string, string | number | null>;
  referral?: Record<string, string | number | null> | null;
}

export const getEventDetails = (code: number, kind: string) =>
  get<EventDetails>(`/admin/event-details/${code}?kind=${kind}`);

// ───────── centers (doc s.6) ─────────
export interface CenterRow {
  id: string;
  name: string;
  province: string | null;
  city: string | null;
  status: string;
  is_active: boolean;
  legacy_code: number | null;
  address: string | null;
  group: string | null;
  clinic_id: string;
}

export const getCenters = (params: string) =>
  get<{
    records_total: number;
    records_filtered: number;
    offset: number;
    columns: string[];
    rows: CenterRow[];
  }>(`/admin/centers${params}`);

export const exportCentersUrl = (params: string) => `/admin/centers/export${params}`;

export const getCenterGroups = () => get<{ id: string; name: string }[]>('/admin/center-groups');
export const createCenterGroup = (body: { name: string; description?: string }) =>
  post<{ id: string; name: string }>('/admin/center-groups', body);
export const createCenter = (body: {
  name: string;
  province_code: number;
  city: string;
  address?: string;
  group_id?: string;
}) => post<CenterRow>('/admin/centers', body);
export const getCenterDetail = (id: string) => get<CenterRow & { clinic_name: string | null }>(
  `/admin/centers/${id}`,
);

// ───────── reports (doc s.7 / s.8) ─────────
export interface ReportGroup {
  title: string;
  description: string;
  icon: string;
  gradient: string;
  cards: {
    title: string;
    description: string;
    path: string;
    icon: string;
    gradient: string;
  }[];
}

export const getReports = () => get<{ groups: ReportGroup[] }>('/admin/reports');

export interface EventReportData {
  kind: string;
  state: string;
  total: number;
  rows: {
    code: number;
    service: string | null;
    consultant: string | null;
    branch: string | null;
    referral_code: number | null;
    status_fa: string | null;
    start_at: string;
    end_at: string;
  }[];
}

export const getEventReport = (kind: string, state: string, params = '') =>
  get<EventReportData>(`/admin/reports/events?kind=${kind}&state=${state}${params}`);

export const getInvitedPersons = (params = '') =>
  get<{ total: number; rows: Record<string, string | number | null>[] }>(
    `/admin/reports/invited${params}`,
  );

export const getReservationRequests = (params = '') =>
  get<{ total: number; rows: Record<string, string | number | null>[] }>(
    `/admin/reports/reservation-requests${params}`,
  );

export interface ConsultantReportRow {
  row: number;
  name: string;
  national_id: string | null;
  mobile: string | null;
  degree: string | null;
  level: string | null;
  services: { province: string | null; city: string | null; branch: string | null; service: string | null; count: number; amount: number }[];
  total_count: number;
  total_amount: number;
}

export const getConsultantReport = (groupBy: string) =>
  get<{ rows: ConsultantReportRow[]; group_by: string }>(
    `/admin/reports/consultants?group_by=${groupBy}`,
  );

// ───────── activity log (doc s.3.1.2 #۲۷) ─────────
export interface LogRow {
  id: string;
  action: string;
  outcome: string;
  actor: string | null;
  actor_phone: string | null;
  resource_type: string | null;
  resource_id: string | null;
  request_id: string | null;
  ip: string | null;
  created_at: string;
}

export const getLogs = (params: string) =>
  get<{ total: number; rows: LogRow[] }>(`/admin/logs${params}`);

// keep the shared api import used for typing parity
export { api };

// ───────────────── release 3 · finance admin (B18-B22) ─────────────────
export interface WalletRow {
  id: string;
  user_id: string;
  currency: string;
  balance: number;
  is_active: boolean;
}

export interface WalletEntryRow {
  id: string;
  direction: 'credit' | 'debit';
  amount: number;
  balance_after: number;
  entry_type: string;
  note: string | null;
  created_at: string;
}

export const getWallets = (q = '') =>
  get<WalletRow[]>(`/wallets${q ? `?q=${encodeURIComponent(q)}` : ''}`);

export const getUserWallet = (userId: string) => get<WalletRow>(`/wallets/${userId}`);

export const getUserWalletEntries = (userId: string) =>
  get<WalletEntryRow[]>(`/wallets/${userId}/entries`);

export const creditUserWallet = (userId: string, amount: number, note?: string, idem?: string) =>
  post<WalletEntryRow>('/wallet/credits', { user_id: userId, amount, note: note || null }, idem);

export interface DiscountRow {
  id: string;
  code: string;
  kind: 'percent' | 'fixed';
  value: number;
  min_order_amount: number;
  max_redemptions_total: number | null;
  max_redemptions_per_user: number | null;
  starts_at: string | null;
  ends_at: string | null;
  is_active: boolean;
}

export const getDiscounts = () => get<DiscountRow[]>('/discounts');

export const createDiscount = (body: Record<string, unknown>) => post<DiscountRow>('/discounts', body);

export interface RefundRow {
  id: string;
  order_id: string;
  user_id: string;
  amount: number;
  reason: string;
  status: string;
  decision_note: string | null;
  created_at: string;
  executed_amount: number | null;
}

export const getRefunds = () => get<RefundRow[]>('/refund-requests');

export const refundAction = (id: string, action: 'review' | 'approve' | 'reject' | 'execute', note?: string) =>
  post<RefundRow>(`/refund-requests/${id}/${action}`, note ? { note } : {});

export interface AccountRow {
  id: string;
  code: string;
  name: string;
  kind: string;
  balance: number;
}

export interface JournalRow {
  id: string;
  entry_no: string;
  description: string | null;
  source_type: string | null;
  posted_at: string;
  lines: { account_code: string | null; account_name: string | null; debit: number; credit: number }[];
}

export const getAccounts = () => get<AccountRow[]>('/accounts');
export const createAccount = (body: { code: string; name: string; kind: string }) =>
  post<AccountRow>('/accounts', body);
export const getJournalEntries = () => get<JournalRow[]>('/journal-entries');
export const createJournalEntry = (body: {
  description?: string;
  lines: { account_id: string; debit: number; credit: number }[];
}) => post<JournalRow>('/journal-entries', body);

export interface SettlementRow {
  id: string;
  consultant_id: string;
  period_from: string;
  period_to: string;
  gross_amount: number;
  share_percent: number;
  net_amount: number;
  status: string;
  paid_at: string | null;
}

export const getSettlements = () => get<SettlementRow[]>('/settlements');
export const createSettlement = (body: Record<string, unknown>) => post<SettlementRow>('/settlements', body);
export const advanceSettlement = (id: string) => post<SettlementRow>(`/settlements/${id}/advance`, {});
