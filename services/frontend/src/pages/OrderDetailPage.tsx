import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, type OrderActionName, type Position, type WorkflowAction } from '../api';
import { ErrorState, Loading } from '../components/Feedback';
import { SegmentBar } from '../components/SegmentBar';
import { KindTag, OrderTag, Tag } from '../components/StatusTag';
import { TaskChips } from '../components/TaskChips';
import { useEventStream } from '../hooks/useEventStream';
import { useResource } from '../hooks/useResource';
import { useI18n } from '../i18n';

const LEVEL_TONE = { INFO: 'muted', WARN: 'wait', ERROR: 'fail' } as const;

/** The one quick action that makes sense for a position in its current state. */
function quickAction(p: Position): WorkflowAction | null {
  if (p.status === 'FAILED') return { action: 'retry' };
  if (p.status === 'RUNNING' || p.status === 'WAITING') return { action: 'pause' };
  if (p.status === 'PAUSED') return { action: 'resume' };
  return null;
}

export function OrderDetailPage() {
  const { orderId } = useParams();
  const id = Number(orderId);
  const { t, fmt } = useI18n();
  const order = useResource(() => api.getOrder(id), [id]);
  const activity = useResource(() => api.listEvents({ order_id: id }, 8), [id]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<Error>();

  useEventStream({ order_id: id }, () => {
    order.reload();
    activity.reload();
  });

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setActionError(undefined);
    try {
      await fn();
      order.reload();
      activity.reload();
    } catch (err) {
      setActionError(err as Error);
    } finally {
      setBusy(false);
    }
  }

  if (order.error) return <ErrorState error={order.error} onRetry={order.reload} />;
  if (!order.data) return <Loading />;
  const o = order.data;
  const isQuote = o.kind === 'QUOTE';
  const statuses = o.positions.map((p) => p.status);
  const count = (...s: string[]) => statuses.filter((x) => s.includes(x)).length;
  const failed = count('FAILED');
  const bulk = (action: OrderActionName) => run(() => api.orderAction(o.id, action));

  return (
    <div className="stack-md">
      <nav aria-label="Breadcrumb" className="crumb">
        <Link to="/orders">{t('order.breadcrumb')}</Link> <span aria-hidden="true">/</span> <span className="crumb__here">{o.number}</span>
      </nav>

      <section className="card card--top pad-lg stack-md">
        <div className="page-head">
          <div className="stack-xs">
            <div className="wrap">
              <span className="mono strong">{o.number}</span>
              <KindTag kind={o.kind} />
              <OrderTag status={o.status} />
              {o.overdue && <span className="flag">{t('orders.overdue')}</span>}
            </div>
            <h1 className="h1 h1--sm">{o.title}</h1>
          </div>
          <div className="wrap">
            {isQuote && o.status === 'AWAITING_ACCEPTANCE' && (
              <>
                <button type="button" className="btn" disabled={busy} onClick={() => run(() => api.rejectQuote(o.id))}>
                  {t('order.reject')}
                </button>
                <button type="button" className="btn btn--primary" disabled={busy} onClick={() => run(() => api.acceptQuote(o.id))}>
                  {t('order.accept')}
                </button>
              </>
            )}
            {!isQuote && (
              <>
                <button type="button" className="btn" disabled={busy || count('RUNNING', 'WAITING') === 0} onClick={() => bulk('pause')}>
                  {t('order.pauseAll')}
                </button>
                <button type="button" className="btn" disabled={busy || count('PAUSED') === 0} onClick={() => bulk('resume')}>
                  {t('order.resumeAll')}
                </button>
                <button type="button" className={`btn${failed ? ' btn--danger-solid' : ''}`} disabled={busy || failed === 0} onClick={() => bulk('retry_failed')}>
                  {t('order.retryFailed', { n: failed })}
                </button>
              </>
            )}
            {(o.plunet_order_id ?? o.plunet_quote_id) && (
              <a href="https://portal.foxtranslations.com/" target="_blank" rel="noopener noreferrer" className="btn btn--link">
                {t('common.openInPlunet')} ↗
              </a>
            )}
          </div>
        </div>

        {isQuote && o.status === 'AWAITING_ACCEPTANCE' && (
          <div className="banner banner--muted">
            <strong className="label-strong">{t('orderStatus.AWAITING_ACCEPTANCE')}</strong>
            <span>{t('order.quoteBanner')}</span>
          </div>
        )}
        {actionError && <ErrorState error={actionError} />}

        <dl className="meta">
          {[
            [t('order.meta.customer'), o.customer?.name],
            [t('order.meta.pm'), o.pm?.name],
            [t('order.meta.deadline'), o.deadline ? fmt.date(o.deadline) : null],
            [t('order.meta.template'), o.template.name],
            [t('order.meta.returnTrip'), t(`dest.${o.default_destination}`)],
            [t('order.meta.source'), `${o.source_site ?? ''} · ${o.source_lang}`],
          ].map(([k, v]) => (
            <div key={k} className="stack-0">
              <dt className="label">{k}</dt>
              <dd className="strong small">{v ?? t('common.none')}</dd>
            </div>
          ))}
        </dl>

        <div className="stack-xs">
          <SegmentBar statuses={statuses} tall />
          <span className="mono small muted">
            {isQuote
              ? t('orders.progress.quote', { total: statuses.length })
              : t('order.progress', { done: count('COMPLETED'), total: statuses.length, running: count('RUNNING', 'WAITING'), failed })}
          </span>
        </div>
      </section>

      <div className="split split--aside">
        <section aria-label={t('order.positions', { n: o.positions.length })} className="card split__main">
          <div className="card__head">
            <h2 className="h3">{t('order.positions', { n: o.positions.length })}</h2>
            <span className="small muted">{t('order.positionsHint')}</span>
          </div>
          <div className="scroll-x">
            <div className="plist">
              <div className="plist__row plist__head">
                <span>#</span>
                <span>{t('order.col.position')}</span>
                <span>{t('order.col.workflow')}</span>
                <span className="right">{t('order.col.control')}</span>
              </div>
              {o.positions.map((p) => {
                const action = quickAction(p);
                const to = `/orders/${o.id}/positions/${p.id}`;
                return (
                  <div key={p.id} className="plist__row">
                    <span className="mono small muted">P{String(p.no).padStart(2, '0')}</span>
                    <Link to={to} className="stack-xs min0 plain">
                      <span className="strong small">{p.title}</span>
                      <span className="wrap wrap--tight">
                        <span className="langpair">{p.source_lang} → {p.target_lang}</span>
                        <span className="mono tiny muted">{t('common.words', { n: fmt.number(p.words) })} · {p.file_name}</span>
                      </span>
                    </Link>
                    <div className="stack-xs">
                      <TaskChips tasks={p.tasks} />
                      <span className={`small ${p.status === 'FAILED' ? 'tone-fg--fail' : 'muted'}`}>
                        <Tag tone={p.status === 'FAILED' ? 'fail' : 'muted'}>{t(`wf.${p.status}`)}</Tag> {p.note}
                      </span>
                    </div>
                    <div className="row-end">
                      {action && (
                        <button
                          type="button"
                          disabled={busy}
                          className={`btn btn--sm${action.action === 'retry' ? ' btn--danger-solid' : ''}`}
                          onClick={() => run(() => api.workflowAction(p.id, action))}
                        >
                          {action.action === 'retry'
                            ? t('wf.action.retry', { task: t(`task.${p.tasks.find((x) => x.status === 'FAILED')?.type ?? 'QA'}`) })
                            : t(action.action === 'pause' ? 'wf.action.pause' : 'wf.action.resume')}
                        </button>
                      )}
                      <Link to={to} className="btn btn--sm btn--icon" aria-label={t('order.openWorkflow')}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                          <path d="M9 6l6 6-6 6" />
                        </svg>
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <aside className="split__aside stack-md">
          <section className="card" aria-label={t('order.stats')}>
            <h2 className="card__head label">{t('order.stats')}</h2>
            <div className="grid-2 grid--cells">
              <div className="cell">
                <span className="small muted">{t('order.stats.elapsed')}</span>
                <span className="mono stat">{fmt.duration(o.totals.elapsed_seconds)}</span>
              </div>
              <div className="cell">
                <span className="small muted">{t('order.stats.words')}</span>
                <span className="mono stat">{fmt.number(o.totals.words)}</span>
              </div>
              <div className="cell">
                <span className="small muted">{t('order.stats.cost')}</span>
                <span className="mono stat">{o.totals.cost !== null ? fmt.money(o.totals.cost, o.totals.currency ?? 'EUR') : t('common.none')}</span>
                <span className="tiny muted">{t('order.stats.cost.sub')}</span>
              </div>
              <div className="cell">
                <span className="small muted">{t('order.stats.errors')}</span>
                <span className={`mono stat${o.totals.errors ? ' tone-fg--fail' : ''}`}>{o.totals.errors}</span>
                <span className="tiny muted">{t('order.stats.errors.sub')}</span>
              </div>
            </div>
          </section>
          <section className="card" aria-label={t('order.activity')}>
            <h2 className="card__head label">{t('order.activity')}</h2>
            <ol className="feed">
              {activity.data?.length === 0 && <li className="empty">{t('order.noActivity')}</li>}
              {[...(activity.data ?? [])].reverse().map((e) => (
                <li key={e.id} className="feed__item">
                  <span className={`dot tone-bg--${e.kind === 'ACTION' ? 'pause' : LEVEL_TONE[e.level]}`} aria-hidden="true" />
                  <span className="stack-0">
                    <span className="small">{e.message}</span>
                    <span className="mono tiny muted">{fmt.dateTime(e.created_at)} · {e.actor}</span>
                  </span>
                </li>
              ))}
            </ol>
          </section>
        </aside>
      </div>
    </div>
  );
}
