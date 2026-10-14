const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export class ApiException extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

let token: string | null = localStorage.getItem('auth_token');

export function setToken(t: string) {
  token = t;
  localStorage.setItem('auth_token', t);
}

export function clearToken() {
  token = null;
  localStorage.removeItem('auth_token');
}

export function getToken() {
  return token;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  const json = (await res.json()) as {
    data: T;
    errors: { code: string; message: string }[] | null;
  };
  if (res.status >= 400 || json.errors) {
    const err = json.errors?.[0];
    throw new ApiException(err?.code || 'HTTP_' + res.status, err?.message || 'خطا');
  }
  return json.data;
}

export const api = {
  requestOtp: (phone: string) =>
    request<{ challenge_id: string; expires_in_seconds: number }>('/auth/otp/request', {
      method: 'POST',
      body: JSON.stringify({ phone }),
    }),

  verifyOtp: (challengeId: string, code: string) =>
    request<{ access_token: string; is_new_user: boolean }>('/auth/otp/verify', {
      method: 'POST',
      body: JSON.stringify({ challenge_id: challengeId, code }),
    }),

  myAppointments: () =>
    request<{ id: string; start_at: string; status: string }[]>('/appointments'),

  notifications: () =>
    request<
      { id: string; title: string; body: string; read: boolean; created_at: string }[]
    >('/notifications'),

  markRead: (id: string) => request(`/notifications/${id}/read`, { method: 'POST' }),

  listServices: () => request<any[]>('/services'),

  listConsultants: () => request<any[]>('/consultants'),

  availability: (consultantId: string, serviceId: string) =>
    request<any>(`/consultants/${consultantId}/availability?service_id=${serviceId}`),

  createHold: (body: { consultant_id: string; service_id: string; start_at: string }) =>
    request<any>('/booking-holds', { method: 'POST', body: JSON.stringify(body) }),

  createAppointment: (holdId: string) =>
    request<any>('/appointments', {
      method: 'POST',
      body: JSON.stringify({ hold_id: holdId }),
    }),

  createOrder: (appointmentId: string, idempotencyKey: string) =>
    request<any>('/orders', {
      method: 'POST',
      body: JSON.stringify({ appointment_id: appointmentId }),
      headers: { 'Idempotency-Key': idempotencyKey },
    }),

  startPayment: (orderId: string) =>
    request<any>('/payments/start', {
      method: 'POST',
      body: JSON.stringify({ order_id: orderId }),
    }),

  paymentCallback: (gatewayRef: string) =>
    request<any>('/payments/callback', {
      method: 'POST',
      body: JSON.stringify({ gateway_ref: gatewayRef, result: 'success' }),
    }),

  getOrder: (orderId: string) => request<any>(`/orders/${orderId}`),

  getInvoice: (invoiceId: string) => request<any>(`/invoices/${invoiceId}`),

  invoicePdfUrl: (invoiceId: string) => `${BASE_URL}/invoices/${invoiceId}.pdf`,

  me: () => request<any>('/me'),

  myEncounters: () => request<any[]>('/encounters/mine'),

  encounterRecord: (encounterId: string) =>
    request<any>(`/encounters/${encounterId}/record`),
};

