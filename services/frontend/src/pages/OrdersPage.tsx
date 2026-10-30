import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, orderLabel, type OrderKind, type OrderSummary } from '../api';
import { ErrorState, Loading } from '../components/Feedback';
import { Kpi } from '../components/Kpi';
import { SegmentBar } from '../components/SegmentBar';
import { KindTag, OrderTag } from '../components/StatusTag';
import { useEventStream } from '../hooks/useEventStream';
import { useResource } from '../hooks/useResource';
import { useI18n } from '../i18n';

const needsAttention = (o: OrderSummary) => o.status === 'NEEDS_ATTENTION' || o.overdue;

export function OrdersPage() {
  const { t, fmt } = useI18n();
  const [kind, setKind] = useState<OrderKind | undefined>();
  const [attention, setAttention] = useState(false);
  const [pmId, setPmId] = useState<number>();
  const [customerId, setCustomerId] = useState<number>();
  const [q, setQ] = useState('');

  // All orders are loaded once and filtered here; the list is small and the KPIs need the full set.
  const orders = useResource(() => api.listOrders(), []);
  const pms = useResource(() => api.listResources(), []);
  const customers = useResource(() => api.listCustomers(), []);
  useEventStream({}, orders.reload);

  const all = useMemo(() => orders.data ?? [], [orders.data]);
  const rows = useMemo(
    () =>
      all
        .filter((o) => !kind || o.kind === kind)
        .filter((o) => !attention || needsAttention(o))
        .filter((o) => !pmId || o.pm?.id === pmId)
        .filter((o) => !customerId || o.customer?.id === customerId)
        .filter((o) => !q || `${orderLabel(o)} ${o.title} ${o.customer?.name}`.toLowerCase().includes(q.toLowerCase())),
    [all, kind, attention, pmId, customerId, q],
  );

  const positions = all.filter((o) => o.kind === 'ORDER').flatMap((o) => o.progress.statuses);
  const count = (s: string) => positions.filter((p) => p === s).length;

  return (
    <div className="stack-lg">
      <div className="page-head">
        <div className="stack-xs">
          <span className="label">{t('orders.kicker')}</span>
          <h1 className="h1">{t('orders.title')}</h1>
        </div>
        <Link to="/orders/new" className="btn btn--primary">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
          {t('orders.new')}
        </Link>
      </div>

      <section aria-label="Overview" className="kpis">
        <Kpi label={t('orders.kpi.running')} value={count('RUNNING')} sub={t('orders.kpi.running.sub')} tone="run" />
        <Kpi label={t('orders.kpi.waiting')} value={count('WAITING')} sub={t('orders.kpi.waiting.sub')} tone="wait" />
        <Kpi label={t('orders.kpi.failed')} value={count('FAILED')} sub={t('orders.kpi.failed.sub')} tone="fail" />
        <Kpi
          label={t('orders.kpi.quotes')}
          value={all.filter((o) => o.status === 'AWAITING_ACCEPTANCE' || o.status === 'ACCEPTED').length}
          sub={t('orders.kpi.quotes.sub')}
        />
      </section>

      <section aria-label={t('orders.title')} className="card">
        <div className="toolbar">
          <div role="group" aria-label={t('orders.filter.type')} className="seg">
            {([undefined, 'ORDER', 'QUOTE'] as const).map((k) => (
              <button key={k ?? 'all'} type="button" className="seg__btn" aria-pressed={kind === k} onClick={() => setKind(k)}>
                {k === undefined ? t('common.all') : k === 'ORDER' ? t('orders.filter.orders') : t('orders.filter.quotes')}
              </button>
            ))}
          </div>
          <button type="button" className={`toggle${attention ? ' toggle--on' : ''}`} aria-pressed={attention} onClick={() => setAttention(!attention)}>
            <span className="dot tone-bg--fail" aria-hidden="true" />
            {t('orders.filter.attention')} · {all.filter(needsAttention).length}
          </button>
          <label className="inline-field">
            {t('orders.filter.pm')}
            <select className="select select--sm" value={pmId ?? ''} onChange={(e) => setPmId(e.target.value ? Number(e.target.value) : undefined)}>
              <option value="">{t('orders.filter.pm.all')}</option>
              {pms.data?.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </label>
          <label className="inline-field">
            {t('orders.filter.customer')}
            <select className="select select--sm" value={customerId ?? ''} onChange={(e) => setCustomerId(e.target.value ? Number(e.target.value) : undefined)}>
              <option value="">{t('orders.filter.customer.all')}</option>
              {customers.data?.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </label>
          <input
            type="search"
            className="input input--sm grow"
            placeholder={t('orders.filter.search')}
            aria-label={t('orders.filter.search')}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>

        {orders.error && <ErrorState error={orders.error} onRetry={orders.reload} />}
        {orders.loading && !orders.data ? (
          <Loading />
        ) : (
          <div className="scroll-x">
            <div className="olist">
              <div className="olist__row olist__head">
                <span>{t('orders.col.number')}</span>
                <span>{t('orders.col.title')}</span>
                <span>{t('orders.col.pm')}</span>
                <span>{t('orders.col.status')}</span>
                <span>{t('orders.col.positions')}</span>
                <span>{t('orders.col.deadline')}</span>
                <span>{t('orders.col.activity')}</span>
                <span />
              </div>
              {rows.map((o) => {
                const done = o.progress.statuses.filter((s) => s === 'COMPLETED').length;
                return (
                  <Link key={o.id} to={`/orders/${o.id}`} className="olist__row olist__link">
                    <span className="stack-xs">
                      <span className="mono strong">{orderLabel(o)}</span>
                      <KindTag kind={o.kind} />
                    </span>
                    <span className="stack-0 min0">
                      <span className="strong">{o.title}</span>
                      <span className="small muted">{o.customer?.name}</span>
                    </span>
                    <span className="small">{o.pm?.name}</span>
                    <span>
                      <OrderTag status={o.status} />
                    </span>
                    <span className="stack-xs">
                      <SegmentBar statuses={o.progress.statuses} />
                      <span className="mono small muted">
                        {o.kind === 'QUOTE'
                          ? t('orders.progress.quote', { total: o.progress.total })
                          : t('orders.progress', { done, total: o.progress.total })}
                      </span>
                    </span>
                    <span className="stack-0">
                      <span className="mono small">{o.deadline ? fmt.date(o.deadline) : t('common.none')}</span>
                      {o.overdue && <span className="flag">{t('orders.overdue')}</span>}
                    </span>
                    <span className="small muted">
                      {o.last_activity ? `${o.last_activity.message} · ${fmt.relative(o.last_activity.at)}` : t('common.none')}
                    </span>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <path d="M9 6l6 6-6 6" />
                    </svg>
                  </Link>
                );
              })}
              {!rows.length && <p className="empty">{t('orders.empty')}</p>}
            </div>
          </div>
        )}

        <div className="legend">
          {(
            [
              ['done', 'legend.completed'],
              ['run', 'legend.running'],
              ['wait', 'legend.waiting'],
              ['pause', 'legend.paused'],
              ['fail', 'legend.failed'],
              ['muted', 'legend.notStarted'],
            ] as const
          ).map(([tone, key]) => (
            <span key={tone} className="legend__item">
              <span className={`legend__swatch tone-bg--${tone}`} aria-hidden="true" />
              {t(key)}
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}
