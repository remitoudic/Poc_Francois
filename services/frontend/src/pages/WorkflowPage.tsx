import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, orderLabel, type EventItem, type Task, type WorkflowAction, type WorkflowStatus } from '../api';
import { Dialog } from '../components/Dialog';
import { ErrorState, Loading } from '../components/Feedback';
import { Kpi } from '../components/Kpi';
import { Tag, TASK_TONE, WorkflowTag, wfTone } from '../components/StatusTag';
import { useEventStream } from '../hooks/useEventStream';
import { useResource } from '../hooks/useResource';
import { useI18n } from '../i18n';

type Tab = 'overview' | 'logs' | 'analytics' | 'file';
type LogFilter = 'all' | 'errors' | 'state' | 'actions';
type DialogKind = 'cancel' | 'restart' | null;

const TABS: Tab[] = ['overview', 'logs', 'analytics', 'file'];
const MARK: Record<Task['status'], string> = { PENDING: '', WAITING: '…', RUNNING: '●', DONE: '✓', FAILED: '!', SKIPPED: '–', CANCELLED: '×' };
const LEVEL_TONE = { INFO: 'muted', WARN: 'wait', ERROR: 'fail' } as const;

/** Controls allowed per workflow state (docs/backend-architecture.md §5.4). */
const CONTROLS: Record<WorkflowStatus, Array<'pause' | 'resume' | 'retry' | 'restart' | 'cancel'>> = {
  NOT_STARTED: [],
  RUNNING: ['pause', 'cancel'],
  WAITING: ['pause', 'cancel'],
  PAUSED: ['resume', 'restart', 'cancel'],
  FAILED: ['retry', 'restart', 'cancel'],
  COMPLETED: ['restart'],
  CANCELLED: [],
};

function matchesFilter(e: EventItem, f: LogFilter): boolean {
  if (f === 'errors') return e.level !== 'INFO';
  if (f === 'state') return e.kind === 'STATE';
  if (f === 'actions') return e.kind === 'ACTION';
  return true;
}

export function WorkflowPage() {
  const { orderId, positionId } = useParams();
  const pid = Number(positionId);
  const { t, fmt } = useI18n();
  const [tab, setTab] = useState<Tab>('overview');
  const [logFilter, setLogFilter] = useState<LogFilter>('all');
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [reason, setReason] = useState('');
  const [restartSeq, setRestartSeq] = useState(0);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<Error>();

  const detail = useResource(() => api.getPosition(pid), [pid]);
  const logs = useResource(() => api.listEvents({ position_id: pid }), [pid]);
  const segments = useResource(() => (tab === 'file' ? api.getSegments(pid) : Promise.resolve(undefined)), [pid, tab]);

  useEventStream({ position_id: pid }, () => {
    detail.reload();
    logs.reload();
    if (tab === 'file') segments.reload();
  });

  async function act(action: WorkflowAction) {
    setBusy(true);
    setActionError(undefined);
    try {
      await api.workflowAction(pid, action);
      setDialog(null);
      detail.reload();
      logs.reload();
    } catch (err) {
      setActionError(err as Error);
    } finally {
      setBusy(false);
    }
  }

  function openDialog(kind: Exclude<DialogKind, null>, defaultSeq = 0) {
    setReason('');
    setActionError(undefined);
    setRestartSeq(defaultSeq);
    setDialog(kind);
  }

  if (detail.error) return <ErrorState error={detail.error} onRetry={detail.reload} />;
  if (!detail.data) return <Loading />;
  const { order, position: p } = detail.data;
  const failedTask = p.tasks.find((x) => x.status === 'FAILED');
  const warnings = p.tasks.flatMap((x) => x.findings ?? []).filter((f) => f.level === 'WARNING');
  const blocking = p.tasks.flatMap((x) => x.findings ?? []).filter((f) => f.level === 'BLOCKING');
  const cost = p.tasks.reduce((n, x) => n + (x.cost ?? 0), 0);
  const firstStart = p.tasks.find((x) => x.started_at)?.started_at;
  const lastEnd = p.status === 'COMPLETED' ? p.tasks[p.tasks.length - 1].finished_at : null;
  const elapsed = firstStart ? ((lastEnd ? Date.parse(lastEnd) : Date.now()) - Date.parse(firstStart)) / 1000 : null;
  const maxDuration = Math.max(1, ...p.tasks.map((x) => x.duration_seconds ?? 0));
  const shownLogs = [...(logs.data ?? [])].reverse().filter((e) => matchesFilter(e, logFilter));
  const no = String(p.no).padStart(2, '0');

  const controlButtons = CONTROLS[p.status].map((c) => {
    if (c === 'pause') return <button key={c} type="button" className="btn btn--primary" disabled={busy} onClick={() => act({ action: 'pause' })}>{t('wf.action.pause')}</button>;
    if (c === 'resume') return <button key={c} type="button" className="btn btn--primary" disabled={busy} onClick={() => act({ action: 'resume' })}>{t('wf.action.resume')}</button>;
    if (c === 'retry') return <button key={c} type="button" className="btn btn--primary" disabled={busy} onClick={() => act({ action: 'retry' })}>{t('wf.action.retry', { task: t(`task.${failedTask?.type ?? 'QA'}`) })}</button>;
    if (c === 'restart') return <button key={c} type="button" className="btn" disabled={busy} onClick={() => openDialog('restart', failedTask ? Math.max(0, failedTask.seq - 1) : 0)}>{t('wf.action.restart')}</button>;
    return <button key={c} type="button" className="btn btn--danger" disabled={busy} onClick={() => openDialog('cancel')}>{t('wf.action.cancel')}</button>;
  });

  return (
    <div className="stack-md">
      <nav aria-label="Breadcrumb" className="crumb">
        <Link to="/orders">{t('order.breadcrumb')}</Link> <span aria-hidden="true">/</span>{' '}
        <Link to={`/orders/${orderId}`}>{orderLabel(order)}</Link> <span aria-hidden="true">/</span>{' '}
        <span className="crumb__here">{t('wf.breadcrumbPosition', { no })}</span>
      </nav>

      <section className="card card--top pad-lg stack-md">
        <div className="page-head">
          <div className="stack-xs">
            <div className="wrap">
              <span className="mono strong">P{no}</span>
              <span className="langpair">{p.source_lang} → {p.target_lang}</span>
              <WorkflowTag status={p.status} />
            </div>
            <h1 className="h1 h1--sm">{p.title}</h1>
            <span className="small muted">
              {t('wf.subtitle', {
                post: p.polylang_post_id ?? '—',
                item: p.plunet_item_id ? `I-${p.plunet_item_id}` : '—',
                template: order.template.name,
                dest: t(`dest.${p.destination}`),
              })}
            </span>
          </div>
          <div role="group" aria-label={t('wf.controls')} className="wrap">
            {controlButtons.length ? controlButtons : <span className="small muted">{t('wf.noControls')}</span>}
          </div>
        </div>
        <div className={`banner banner--${wfTone(p.status)}`}>
          <strong className="label-strong">{failedTask ? `${t(`task.${failedTask.type}`)} · ${t('wf.FAILED')}` : t(`wf.${p.status}`)}</strong>
          <span>{failedTask?.error ? `${failedTask.error}. ` : ''}{t(`wf.banner.${p.status}`)}</span>
        </div>
        {actionError && !dialog && <ErrorState error={actionError} />}
      </section>

      <div role="tablist" aria-label="Workflow views" className="tabs">
        {TABS.map((id) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} className="tab" onClick={() => setTab(id)}>
            <span>{t(`wf.tab.${id}`)}</span>
            <span className="tab__sub">{t(`wf.tab.${id}.sub`)}</span>
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <section className="card" aria-label={t('wf.tab.overview')}>
          <ol className="timeline">
            {p.tasks.map((task) => {
              const tone = task.overlay === 'PAUSED' ? 'pause' : TASK_TONE[task.status];
              return (
                <li key={task.id} className="timeline__row">
                  <span className={`mark mark--${tone}${task.status === 'DONE' || task.status === 'FAILED' ? ' mark--solid' : ''}`} aria-hidden="true">{MARK[task.status]}</span>
                  <span className="stack-0">
                    <span className="strong">{t(`task.${task.type}`)}</span>
                    <span className={`label tone-fg--${tone}`}>{t(`taskStatus.${task.status}`)}</span>
                  </span>
                  <span className="stack-0 min0">
                    <span className="small">{task.error ?? (task.plunet_job_id ? t('wf.plunetJob', { id: task.plunet_job_id, status: task.plunet_job_status ?? '' }) : t('wf.system'))}</span>
                    {task.started_at && <span className="mono tiny muted">{fmt.dateTime(task.started_at)}{task.finished_at ? ` → ${fmt.time(task.finished_at)}` : ''}</span>}
                  </span>
                  <span className="stack-0">
                    <span className="tiny muted">{t('wf.assignee')}</span>
                    <span className="small strong">{task.assignee?.name ?? t('wf.system')}</span>
                  </span>
                  <span className="stack-0">
                    <span className="tiny muted">{t('wf.duration')}</span>
                    <span className="mono small">{task.duration_seconds !== null ? fmt.duration(task.duration_seconds) : t('common.none')}</span>
                  </span>
                  <span className="stack-0">
                    <span className="tiny muted">{t('wf.attempts')}</span>
                    <span className="mono small">{task.attempts}</span>
                  </span>
                </li>
              );
            })}
          </ol>
        </section>
      )}

      {tab === 'logs' && (
        <section className="card" aria-label={t('wf.tab.logs')}>
          <div className="toolbar">
            <div role="group" className="seg">
              {(['all', 'errors', 'state', 'actions'] as const).map((f) => (
                <button key={f} type="button" className="seg__btn" aria-pressed={logFilter === f} onClick={() => setLogFilter(f)}>
                  {t(`wf.logs.${f}`)}
                </button>
              ))}
            </div>
            <span className="live"><span className="dot tone-bg--done" aria-hidden="true" />{t('common.live')}</span>
          </div>
          <div className="scroll-x">
            <div className="logs">
              {shownLogs.length === 0 && <p className="empty">{t('wf.logs.empty')}</p>}
              {shownLogs.map((e) => (
                <div key={e.id} className="logs__row">
                  <span className="muted">{fmt.time(e.created_at)}</span>
                  <span className={`strong tone-fg--${e.kind === 'ACTION' ? 'pause' : e.kind === 'STATE' && e.level === 'INFO' ? 'run' : LEVEL_TONE[e.level]}`}>
                    {e.kind === 'LOG' ? e.level : e.kind === 'STATE' && e.level !== 'INFO' ? e.level : e.kind}
                  </span>
                  <span className="pre-wrap">
                    {e.message}
                    {e.reason && <span className="muted"> · {t('wf.logs.reason', { reason: e.reason })}</span>}
                  </span>
                  <span className="muted right">{e.actor}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {tab === 'analytics' && (
        <div className="stack-md">
          <section className="kpis">
            <Kpi label={t('wf.an.elapsed')} value={elapsed !== null ? fmt.duration(elapsed) : t('common.none')} sub={t('wf.an.elapsed.sub')} />
            <Kpi label={t('wf.an.cost')} value={cost ? fmt.money(cost) : t('common.none')} sub={t('wf.an.cost.sub')} />
            <Kpi label={t('wf.an.errors')} value={blocking.length} sub={t('wf.an.errors.sub', { n: warnings.length })} tone={blocking.length ? 'fail' : undefined} />
            <Kpi label={t('wf.an.words')} value={fmt.number(p.words)} sub={t('wf.an.words.sub', { n: p.segments })} />
          </section>
          <div className="split">
            <section className="card pad-lg stack-sm split__main" aria-label={t('wf.an.timePerTask')}>
              <h2 className="label">{t('wf.an.timePerTask')}</h2>
              {p.tasks.map((task) => (
                <div key={task.id} className="bar-row">
                  <span className="small strong">{t(`task.${task.type}`)}</span>
                  <span className="bar">
                    <span
                      className={`bar__fill tone-bg--${task.status === 'FAILED' ? 'fail' : task.assignee ? 'pause' : 'run'}`}
                      style={{ width: `${task.duration_seconds ? Math.max(1, (task.duration_seconds / maxDuration) * 100) : 0}%` }}
                    />
                  </span>
                  <span className="mono small right">{task.duration_seconds !== null ? fmt.duration(task.duration_seconds) : t('common.none')}</span>
                </div>
              ))}
            </section>
            <section className="card split__aside" aria-label={t('wf.an.findings')}>
              <h2 className="card__head label">{t('wf.an.findings')}</h2>
              <ul className="findings">
                {[...blocking, ...warnings].length === 0 && <li className="empty">{t('wf.an.noFindings')}</li>}
                {[...blocking, ...warnings].map((f, i) => (
                  <li key={i} className="findings__row">
                    <span className="mono tiny muted">{f.unit_id}</span>
                    <span className="small">{f.message}</span>
                    <Tag tone={f.level === 'BLOCKING' ? 'fail' : 'wait'}>{f.level}</Tag>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </div>
      )}

      {tab === 'file' && (
        <section className="card" aria-label={t('wf.tab.file')}>
          <div className="card__head">
            <span className="mono small strong">
              {t('wf.file.summary', { file: p.file_name, segments: p.segments, words: fmt.number(p.words) })}
            </span>
          </div>
          {!segments.data ? (
            <Loading />
          ) : (
            <div className="scroll-x">
              <div className="segs">
                <div className="segs__row segs__head">
                  <span>Unit</span>
                  <span>{t('wf.file.source', { lang: p.source_lang })}</span>
                  <span>{t('wf.file.target', { lang: p.target_lang })}</span>
                  <span>{t('wf.file.qa')}</span>
                </div>
                {segments.data.map((s) => {
                  const bad = s.findings.some((f) => f.level === 'BLOCKING');
                  return (
                    <div key={s.unit_id} className={`segs__row${bad ? ' segs__row--bad' : ''}`}>
                      <span className="mono tiny muted">{s.unit_id}</span>
                      <span className="small">{s.source}</span>
                      <span className={`small${s.target ? '' : ' muted'}`}>{s.target || t('wf.file.notTranslated')}</span>
                      <span className={`label tone-fg--${bad ? 'fail' : s.findings.length ? 'wait' : 'done'}`}>
                        {s.findings.length ? s.findings.map((f) => f.code).join(', ') : s.target ? t('wf.file.ok') : t('common.none')}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </section>
      )}

      {dialog && (
        <Dialog
          title={t(dialog === 'cancel' ? 'wf.dialog.cancel.title' : 'wf.dialog.restart.title')}
          onClose={() => setDialog(null)}
          footer={
            <>
              <button type="button" className="btn" onClick={() => setDialog(null)}>{t('wf.dialog.keep')}</button>
              <button
                type="button"
                className={`btn ${dialog === 'cancel' ? 'btn--danger-solid' : 'btn--primary'}`}
                disabled={busy || (dialog === 'cancel' && !reason.trim())}
                onClick={() =>
                  act(dialog === 'cancel' ? { action: 'cancel', reason } : { action: 'restart_from', task_seq: restartSeq, reason: reason || undefined })
                }
              >
                {t(dialog === 'cancel' ? 'wf.dialog.cancel.confirm' : 'wf.dialog.restart.confirm')}
              </button>
            </>
          }
        >
          <p className="small">{t(dialog === 'cancel' ? 'wf.dialog.cancel.text' : 'wf.dialog.restart.text')}</p>
          {dialog === 'restart' && (
            <label className="field">
              <span className="label">{t('wf.dialog.restart.from')}</span>
              <select className="select" value={restartSeq} onChange={(e) => setRestartSeq(Number(e.target.value))}>
                {p.tasks
                  .filter((task) => task.status !== 'PENDING' || task.seq === 0)
                  .map((task) => (
                    <option key={task.seq} value={task.seq}>{t(`task.${task.type}`)}</option>
                  ))}
              </select>
            </label>
          )}
          <label className="field">
            <span className="label">{t(dialog === 'cancel' ? 'wf.dialog.reasonRequired' : 'wf.dialog.reasonOptional')}</span>
            <textarea className="input textarea" rows={3} value={reason} placeholder={t('wf.dialog.reasonPlaceholder')} onChange={(e) => setReason(e.target.value)} />
          </label>
          {actionError && <ErrorState error={actionError} />}
        </Dialog>
      )}
    </div>
  );
}
