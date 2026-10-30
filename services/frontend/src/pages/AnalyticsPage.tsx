import { useState } from 'react';
import { api } from '../api';
import { ErrorState, Loading } from '../components/Feedback';
import { Kpi } from '../components/Kpi';
import { useEventStream } from '../hooks/useEventStream';
import { useResource } from '../hooks/useResource';
import { useI18n } from '../i18n';

type GroupBy = 'pm' | 'customer';

export function AnalyticsPage() {
  const { t, fmt } = useI18n();
  const [groupBy, setGroupBy] = useState<GroupBy>('pm');
  const summary = useResource(() => api.analytics(groupBy), [groupBy]);
  useEventStream({}, summary.reload, undefined, 2000);

  const rows = summary.data?.rows ?? [];
  const currency = summary.data?.currency ?? 'EUR';
  const sum = (k: 'orders' | 'positions' | 'completed' | 'cost' | 'errors') => rows.reduce((n, r) => n + r[k], 0);
  const maxCost = Math.max(1, ...rows.map((r) => r.cost));

  return (
    <div className="stack-lg">
      <div className="page-head">
        <div className="stack-xs">
          <span className="label">{t('analytics.kicker')}</span>
          <h1 className="h1">{t('analytics.title')}</h1>
        </div>
        <div role="group" className="seg">
          {(['pm', 'customer'] as const).map((g) => (
            <button key={g} type="button" className="seg__btn" aria-pressed={groupBy === g} onClick={() => setGroupBy(g)}>
              {t(g === 'pm' ? 'analytics.byPm' : 'analytics.byCustomer')}
            </button>
          ))}
        </div>
      </div>

      <section aria-label="Totals" className="kpis">
        <Kpi label={t('analytics.col.orders')} value={sum('orders')} />
        <Kpi label={t('analytics.col.positions')} value={sum('positions')} sub={`${sum('completed')} ${t('analytics.col.completed').toLowerCase()}`} />
        <Kpi label={t('analytics.col.cost')} value={fmt.money(sum('cost'), currency)} />
        <Kpi label={t('analytics.col.errors')} value={sum('errors')} tone={sum('errors') ? 'fail' : undefined} />
      </section>

      <section className="card" aria-label={t(groupBy === 'pm' ? 'analytics.byPm' : 'analytics.byCustomer')}>
        {summary.error && <ErrorState error={summary.error} onRetry={summary.reload} />}
        {!summary.data ? (
          <Loading />
        ) : (
          <div className="scroll-x">
            <div className="alist">
              <div className="alist__row alist__head">
                <span>{t('analytics.col.name')}</span>
                <span className="right">{t('analytics.col.orders')}</span>
                <span className="right">{t('analytics.col.positions')}</span>
                <span className="right">{t('analytics.col.completed')}</span>
                <span className="right">{t('analytics.col.duration')}</span>
                <span>{t('analytics.col.cost')}</span>
                <span className="right">{t('analytics.col.errors')}</span>
              </div>
              {rows.map((r) => (
                <div key={r.key} className="alist__row">
                  <span className="strong small">{r.label}</span>
                  <span className="mono small right">{r.orders}</span>
                  <span className="mono small right">{r.positions}</span>
                  <span className="mono small right">{r.completed}</span>
                  <span className="mono small right">
                    {r.avg_duration_hours !== null ? t('analytics.hours', { n: fmt.number(Math.round(r.avg_duration_hours * 10) / 10) }) : t('common.none')}
                  </span>
                  <span className="bar-cell">
                    <span className="bar">
                      <span className="bar__fill tone-bg--run" style={{ width: `${(r.cost / maxCost) * 100}%` }} />
                    </span>
                    <span className="mono small">{fmt.money(r.cost, currency)}</span>
                  </span>
                  <span className={`mono small right${r.errors ? ' tone-fg--fail' : ''}`}>{r.errors}</span>
                </div>
              ))}
              {!rows.length && <p className="empty">{t('common.none')}</p>}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
