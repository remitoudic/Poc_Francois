import {
  ApiError,
  type Api,
  type EventItem,
  type EventScope,
  type OrderFilters,
} from './types';

const BASE = '/api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      // keep statusText
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

function query(params: Record<string, string | number | boolean | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : '';
}

function scopeQuery(scope: EventScope) {
  return { order_id: scope.order_id, position_id: scope.position_id };
}

export const httpApi: Api = {
  mode: 'http',
  listOrders: (f: OrderFilters = {}) =>
    request(
      `/orders${query({ kind: f.kind, attention: f.attention || undefined, pm: f.pm_id, customer: f.customer_id, q: f.q })}`,
    ),
  getOrder: (id) => request(`/orders/${id}`),
  createOrder: (req) => post('/orders', req),
  acceptQuote: (id) => post(`/orders/${id}/accept`),
  rejectQuote: (id) => post(`/orders/${id}/reject`),
  orderAction: (id, action) => post(`/orders/${id}/actions`, { action }),
  getPosition: (id) => request(`/positions/${id}`),
  workflowAction: (id, action) => post(`/positions/${id}/actions`, action),
  listEvents: (scope, limit = 500) => request(`/events${query({ ...scopeQuery(scope), limit })}`),
  getSegments: (id) => request(`/positions/${id}/segments`),
  listCustomers: () => request('/plunet/customers'),
  listResources: () => request('/plunet/resources'),
  listTemplates: () => request('/templates'),
  listSites: () => request('/sources/polylang/sites'),
  listLanguages: (site) => request(`/sources/polylang/languages${query({ site })}`),
  listPosts: (site, lang) => request(`/sources/polylang/posts${query({ site, lang })}`),
  analytics: (groupBy) => request(`/analytics/summary${query({ group_by: groupBy })}`),

  subscribe(scope, onEvent, onResync) {
    // EventSource reconnects by itself and sends Last-Event-ID, so the server replays missed events.
    const source = new EventSource(`${BASE}/events/stream${query(scopeQuery(scope))}`);
    const handle = (msg: MessageEvent) => onEvent(JSON.parse(msg.data) as EventItem);
    for (const kind of ['log', 'state', 'action']) source.addEventListener(kind, handle);
    source.addEventListener('resync', () => onResync?.());
    return () => source.close();
  },
};
