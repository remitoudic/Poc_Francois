// In-memory mock of the v2 API, with a small simulation of Temporal workflows and Plunet:
// tasks advance on a timer, human tasks wait on "Plunet", QA can fail, controls follow
// docs/backend-architecture.md §5.4. State lives in memory and resets on page reload.

import {
  ApiError,
  type AnalyticsRow,
  type Api,
  type CreateOrderRequest,
  type Destination,
  type EventItem,
  type EventKind,
  type EventLevel,
  type EventScope,
  type OrderDetail,
  type OrderKind,
  type OrderStatus,
  type OrderSummary,
  type Position,
  type PositionDetail,
  type QaFinding,
  type Ref,
  type Segment,
  type Task,
  type TaskStatus,
  type TaskType,
  type Template,
  type WorkflowAction,
  type WorkflowStatus,
} from '../types';
import { getActor } from '../actor';
import { CUSTOMERS, LANGUAGES, LINGUISTS, POSTS, POST_WORDS, RESOURCES, SITES, TEMPLATES, type SeedPost } from './seed';

const TICK_MS = 3000;
const LATENCY_MS = 120;
const HUMAN: TaskType[] = ['PM', 'TRA', 'REV'];
/** Simulation speed: ticks spent waiting for assignment / working, per task type. */
const TICKS: Record<TaskType, { wait: number; run: number }> = {
  IMPORT: { wait: 0, run: 1 },
  PM: { wait: 1, run: 2 },
  TRA: { wait: 2, run: 5 },
  REV: { wait: 2, run: 3 },
  QA: { wait: 0, run: 1 },
  DELIVER: { wait: 0, run: 1 },
};
/** Typical durations used for seeded (historical) tasks, in seconds. */
const SEED_DURATION: Record<TaskType, number> = { IMPORT: 4, PM: 2100, TRA: 7800, REV: 3100, QA: 9, DELIVER: 5 };
const RATE_PER_WORD: Partial<Record<TaskType, number>> = { TRA: 0.12, REV: 0.05 };
const PM_FLAT_FEE = 45;
const PLACEHOLDER = /\{[^}]*\}|%(?:\d+\$)?[sd]/g;

interface MTask {
  id: number;
  seq: number;
  type: TaskType;
  status: TaskStatus;
  overlay: 'FAILED' | 'PAUSED' | null;
  plunet_job_id: number | null;
  plunet_job_status: string | null;
  assignee: Ref | null;
  attempts: number;
  failures: number;
  cost: number | null;
  started_at: number | null;
  finished_at: number | null;
  error: string | null;
  findings: QaFinding[] | null;
  ticks: number;
}

interface MPosition {
  id: number;
  order_id: number;
  no: number;
  post: SeedPost;
  target_lang: string;
  plunet_item_id: number | null;
  words: number;
  destination: Destination;
  destination_url: string | null;
  paused: boolean;
  cancelled: boolean;
  translated: boolean;
  qaWillFail: boolean;
  note: string | null;
  tasks: MTask[];
}

interface MOrder {
  id: number;
  kind: OrderKind;
  number: string;
  title: string;
  customer: Ref;
  pm: Ref;
  deadline: number | null;
  template: Template;
  default_destination: Destination;
  destination_url: string | null;
  source_site: string;
  source_lang: string;
  plunet_order_id: number | null;
  plunet_quote_id: number | null;
  created_at: number;
  rejected: boolean;
  /** Ticks since the quote was accepted; the simulated PM converts it after CONVERT_TICKS. */
  accepted: number | null;
  positions: MPosition[];
}

type Listener = { scope: EventScope; onEvent: (e: EventItem) => void };

const ids = { order: 100, position: 1000, task: 10000, event: 0, job: 88200, item: 5100, orderNo: 413, quoteNo: 100 };
const orders: MOrder[] = [];
const events: EventItem[] = [];
const listeners = new Set<Listener>();
const now = () => Date.now();
const iso = (t: number | null) => (t === null ? null : new Date(t).toISOString());
const H = 3600_000;
const year = new Date().getFullYear();

// ---------------------------------------------------------------- derived state

function currentTask(p: MPosition): MTask | undefined {
  return p.tasks.find((t) => t.status !== 'DONE' && t.status !== 'SKIPPED' && t.status !== 'CANCELLED');
}

function orderOf(p: MPosition): MOrder {
  return orders.find((o) => o.id === p.order_id)!;
}

function workflowStatus(p: MPosition): WorkflowStatus {
  if (p.cancelled) return 'CANCELLED';
  if (orderOf(p).kind === 'QUOTE') return 'NOT_STARTED';
  const current = currentTask(p);
  if (!current) return 'COMPLETED';
  if (current.status === 'FAILED') return 'FAILED';
  if (p.paused) return 'PAUSED';
  if (current.status === 'WAITING') return 'WAITING';
  return 'RUNNING';
}

function orderStatus(o: MOrder): OrderStatus {
  if (o.kind === 'QUOTE') return o.rejected ? 'REJECTED' : o.accepted !== null ? 'ACCEPTED' : 'AWAITING_ACCEPTANCE';
  const statuses = o.positions.map(workflowStatus);
  if (statuses.every((s) => s === 'CANCELLED')) return 'CANCELLED';
  if (statuses.every((s) => s === 'COMPLETED' || s === 'CANCELLED')) return 'COMPLETED';
  if (statuses.some((s) => s === 'FAILED' || s === 'PAUSED')) return 'NEEDS_ATTENTION';
  return 'RUNNING';
}

function positionNote(p: MPosition): string | null {
  const status = workflowStatus(p);
  const t = currentTask(p);
  if (status === 'NOT_STARTED') return orderOf(p).accepted !== null ? 'Starts when the PM converts the quote into an order in Plunet' : 'Starts when the quote is accepted';
  if (status === 'PAUSED') return 'Paused · tasks assigned to people continue in Plunet';
  if (status === 'CANCELLED') return 'Cancelled';
  if (status === 'COMPLETED') return p.note;
  if (!t) return p.note;
  if (t.status === 'FAILED') return t.error;
  if (t.status === 'WAITING') return `${label(t.type)} assigned to ${t.assignee?.name ?? '—'} in Plunet`;
  if (t.status === 'RUNNING' && HUMAN.includes(t.type)) {
    const pct = Math.min(95, Math.round((t.ticks / TICKS[t.type].run) * 100));
    return `${label(t.type)} in progress · ${pct}%`;
  }
  return `${label(t.type)} running`;
}

function label(type: TaskType): string {
  return { IMPORT: 'Import', PM: 'PM', TRA: 'Translation', REV: 'Review', QA: 'QA', DELIVER: 'Delivery' }[type];
}

// ---------------------------------------------------------------- DTOs

function taskDto(t: MTask): Task {
  const end = t.finished_at ?? (t.started_at ? now() : null);
  return {
    id: t.id,
    seq: t.seq,
    type: t.type,
    status: t.status,
    overlay: t.overlay,
    plunet_job_id: t.plunet_job_id,
    plunet_job_status: t.plunet_job_status,
    assignee: t.assignee,
    attempts: t.attempts,
    cost: t.cost,
    currency: t.cost === null ? null : 'EUR',
    started_at: iso(t.started_at),
    finished_at: iso(t.finished_at),
    duration_seconds: t.started_at && end ? Math.round((end - t.started_at) / 1000) : null,
    error: t.error,
    findings: t.findings,
  };
}

function positionDto(p: MPosition): Position {
  return {
    id: p.id,
    order_id: p.order_id,
    no: p.no,
    title: p.post.title,
    polylang_post_id: p.post.id,
    source_lang: p.post.lang,
    target_lang: p.target_lang,
    plunet_item_id: p.plunet_item_id,
    file_name: `p${p.post.id}.${p.target_lang}.xlf`,
    words: p.words,
    segments: p.post.segments.length,
    destination: p.destination,
    destination_url: p.destination_url,
    status: workflowStatus(p),
    note: positionNote(p),
    tasks: p.tasks.map(taskDto),
  };
}

function lastActivity(o: MOrder) {
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].order_id === o.id) return { message: events[i].message, at: events[i].created_at };
  }
  return null;
}

function summaryDto(o: MOrder): OrderSummary {
  const status = orderStatus(o);
  return {
    id: o.id,
    kind: o.kind,
    status,
    number: o.number,
    title: o.title,
    customer: o.customer,
    pm: o.pm,
    deadline: iso(o.deadline),
    overdue: o.deadline !== null && o.deadline < now() && o.kind === 'ORDER' && status !== 'COMPLETED' && status !== 'CANCELLED',
    progress: { total: o.positions.length, statuses: o.positions.map(workflowStatus) },
    last_activity: lastActivity(o),
  };
}

function detailDto(o: MOrder): OrderDetail {
  const tasks = o.positions.flatMap((p) => p.tasks);
  const costs = tasks.map((t) => t.cost).filter((c): c is number => c !== null);
  const starts = tasks.map((t) => t.started_at).filter((s): s is number => s !== null);
  return {
    ...summaryDto(o),
    template: { code: o.template.code, name: o.template.name },
    default_destination: o.default_destination,
    destination_url: o.destination_url,
    source_site: o.source_site,
    source_lang: o.source_lang,
    plunet_order_id: o.plunet_order_id,
    plunet_quote_id: o.plunet_quote_id,
    created_at: iso(o.created_at)!,
    positions: o.positions.map(positionDto),
    totals: {
      words: o.positions.reduce((n, p) => n + p.words, 0),
      cost: costs.length ? Math.round(costs.reduce((a, b) => a + b, 0) * 100) / 100 : null,
      currency: costs.length ? 'EUR' : null,
      errors: tasks.reduce((n, t) => n + t.failures, 0),
      elapsed_seconds: starts.length ? Math.round((now() - Math.min(...starts)) / 1000) : 0,
    },
  };
}

function positionDetailDto(p: MPosition): PositionDetail {
  const o = orderOf(p);
  return {
    order: { id: o.id, number: o.number, title: o.title, kind: o.kind, template: { code: o.template.code, name: o.template.name } },
    position: positionDto(p),
  };
}

// ---------------------------------------------------------------- events

function emit(
  message: string,
  opts: { p?: MPosition; o?: MOrder; t?: MTask; kind?: EventKind; level?: EventLevel; actor?: string; reason?: string | null; at?: number; data?: Record<string, unknown> } = {},
): void {
  const order = opts.o ?? (opts.p ? orderOf(opts.p) : undefined);
  const event: EventItem = {
    id: ++ids.event,
    created_at: iso(opts.at ?? now())!,
    kind: opts.kind ?? 'LOG',
    level: opts.level ?? 'INFO',
    order_id: order?.id ?? null,
    position_id: opts.p?.id ?? null,
    task_id: opts.t?.id ?? null,
    actor: opts.actor ?? 'system',
    message: opts.p ? `P${String(opts.p.no).padStart(2, '0')} · ${message}` : message,
    reason: opts.reason ?? null,
    data: opts.data ?? null,
  };
  events.push(event);
  for (const l of listeners) {
    if (l.scope.position_id !== undefined && l.scope.position_id !== event.position_id) continue;
    if (l.scope.order_id !== undefined && l.scope.order_id !== event.order_id) continue;
    l.onEvent(event);
  }
}

// ---------------------------------------------------------------- task transitions

function assignee(p: MPosition, type: TaskType): Ref | null {
  const crew = LINGUISTS[p.target_lang] ?? LINGUISTS.fr;
  if (type === 'TRA') return crew.tra;
  if (type === 'REV') return crew.rev;
  if (type === 'PM') return orderOf(p).pm;
  return null;
}

function startTask(p: MPosition, t: MTask, at = now()): void {
  t.attempts += 1;
  t.started_at = at;
  t.finished_at = null;
  t.ticks = 0;
  t.overlay = null;
  t.error = null;
  if (HUMAN.includes(t.type)) {
    t.plunet_job_id ??= ++ids.job;
    t.assignee = assignee(p, t.type);
    t.status = 'WAITING';
    t.plunet_job_status = 'ASSIGNED_WAITING';
    emit(`${label(t.type)} job J-${t.plunet_job_id} created in Plunet, assigned to ${t.assignee?.name}`, { p, t, kind: 'STATE', at, actor: 'plunet' });
  } else {
    t.status = 'RUNNING';
    emit(`${label(t.type)} started${t.attempts > 1 ? ` (attempt ${t.attempts})` : ''}`, { p, t, kind: 'STATE', at });
  }
}

function qaFindings(p: MPosition): QaFinding[] {
  const findings: QaFinding[] = [];
  p.post.segments.forEach((s, i) => {
    const ph = s.match(PLACEHOLDER);
    if (ph) findings.push({ code: 'PLACEHOLDER_MISMATCH', level: 'BLOCKING', unit_id: `u-${String(i + 1).padStart(3, '0')}`, message: `Placeholder ${ph[0]} missing in target` });
  });
  findings.push({ code: 'LENGTH', level: 'WARNING', unit_id: 'u-001', message: 'Target is 162% of the source length' });
  return findings;
}

function finishTask(p: MPosition, t: MTask, at = now()): void {
  t.ticks = 0;
  if (t.type === 'QA' && p.qaWillFail) {
    p.qaWillFail = false;
    const findings = qaFindings(p);
    const blocking = findings.filter((f) => f.level === 'BLOCKING');
    t.status = 'FAILED';
    t.overlay = 'FAILED';
    t.failures += 1;
    t.findings = findings;
    t.finished_at = at;
    t.error = `QA failed: ${blocking.length} placeholder mismatches (${blocking.map((f) => f.unit_id).join(', ')})`;
    emit(t.error, { p, t, kind: 'STATE', level: 'ERROR', at });
    return;
  }
  t.status = 'DONE';
  t.finished_at = at;
  if (HUMAN.includes(t.type)) {
    t.plunet_job_status = 'DELIVERED';
    t.cost = t.type === 'PM' ? PM_FLAT_FEE : Math.round(p.words * (RATE_PER_WORD[t.type] ?? 0) * 100) / 100;
  }
  if (t.type === 'QA') t.findings = qaFindings(p).filter((f) => f.level === 'WARNING');
  if (t.type === 'TRA') p.translated = true;
  if (t.type === 'IMPORT') emit(`Imported ${p.post.id === 0 ? 'file' : `post #${p.post.id}`} → p${p.post.id}.${p.target_lang}.xlf (${p.post.segments.length} segments)`, { p, t, at });
  if (t.type === 'DELIVER') {
    const postId = p.post.id + 100 + p.no;
    p.note = p.destination === 'POLYLANG' ? `Delivered to Polylang as post #${postId}` : p.destination === 'ENDPOINT' ? 'Delivered to endpoint' : 'Ready for download';
    emit(p.note, { p, t, kind: 'STATE', at });
    return;
  }
  const suffix = HUMAN.includes(t.type) ? ` · Plunet job J-${t.plunet_job_id} → DELIVERED` : '';
  emit(`${label(t.type)} done${suffix}`, { p, t, kind: 'STATE', at, actor: HUMAN.includes(t.type) ? 'plunet' : 'system' });
}

function stepPosition(p: MPosition): void {
  if (p.cancelled || orderOf(p).kind === 'QUOTE') return;
  const t = currentTask(p);
  if (!t || t.status === 'FAILED') return;
  if (t.status === 'PENDING') {
    if (!p.paused) startTask(p, t);
    return;
  }
  t.ticks += 1;
  if (t.status === 'WAITING' && t.ticks >= TICKS[t.type].wait) {
    t.status = 'RUNNING';
    t.plunet_job_status = 'IN_PROGRESS';
    t.ticks = 0;
    emit(`${label(t.type)} started by ${t.assignee?.name} · Plunet job J-${t.plunet_job_id} → IN_PROGRESS`, { p, t, kind: 'STATE', actor: 'plunet' });
  } else if (t.status === 'RUNNING' && t.ticks >= TICKS[t.type].run) {
    finishTask(p, t);
  }
}

const CONVERT_TICKS = 4;

/** The PM converts an accepted quote into an order in Plunet; FOX MLO picks it up. */
function convertQuote(o: MOrder): void {
  o.kind = 'ORDER';
  o.accepted = null;
  o.number = `AU-${year}-${String(++ids.orderNo).padStart(4, '0')}`;
  o.plunet_order_id = 97600 + o.id;
  o.positions.forEach((p) => (p.plunet_item_id = ++ids.item));
  emit(`Quote converted into Plunet order ${o.number}; workflows start`, { o, kind: 'STATE', actor: 'plunet' });
  o.positions.forEach((p) => startTask(p, p.tasks[0]));
}

function tick(): void {
  for (const o of orders) {
    if (o.kind === 'QUOTE' && o.accepted !== null && !o.rejected && ++o.accepted >= CONVERT_TICKS) convertQuote(o);
    for (const p of o.positions) stepPosition(p);
  }
}

// ---------------------------------------------------------------- building orders

function buildPosition(o: MOrder, post: SeedPost, lang: string, no: number, destination: Destination, url: string | null): MPosition {
  const p: MPosition = {
    id: ++ids.position,
    order_id: o.id,
    no,
    post,
    target_lang: lang,
    plunet_item_id: o.kind === 'ORDER' ? ++ids.item : null,
    words: POST_WORDS[post.id] ?? 300,
    destination,
    destination_url: url,
    paused: false,
    cancelled: false,
    translated: false,
    qaWillFail: !!post.qaFailsFirst,
    note: null,
    tasks: [],
  };
  p.tasks = o.template.tasks.map((type, seq) => ({
    id: ++ids.task, seq, type, status: 'PENDING', overlay: null, plunet_job_id: null, plunet_job_status: HUMAN.includes(type) ? 'IN_PREPERATION' : null,
    assignee: null, attempts: 0, failures: 0, cost: null, started_at: null, finished_at: null, error: null, findings: null, ticks: 0,
  }));
  return p;
}

type SeedStage = 'done' | 'not_started' | { at: TaskType; status: 'WAITING' | 'RUNNING' | 'FAILED'; ticks?: number; paused?: boolean };

/** Put a seeded position in a given stage, with plausible history ending `endsAgo` ms before now. */
function seedStage(p: MPosition, stage: SeedStage, endsAgo: number): void {
  if (stage === 'not_started') return;
  const stopAt = stage === 'done' ? p.tasks.length : p.tasks.findIndex((t) => t.type === stage.at);
  let clock = now() - endsAgo - p.tasks.slice(0, stopAt).reduce((n, t) => n + SEED_DURATION[t.type] * 1000, 0);
  for (const t of p.tasks.slice(0, stopAt)) {
    if (t.type === 'QA') p.qaWillFail = false;
    startTask(p, t, clock);
    if (HUMAN.includes(t.type)) {
      t.status = 'RUNNING';
      t.plunet_job_status = 'IN_PROGRESS';
      emit(`${label(t.type)} started by ${t.assignee?.name} · Plunet job J-${t.plunet_job_id} → IN_PROGRESS`, { p, t, kind: 'STATE', actor: 'plunet', at: clock + 600_000 });
    }
    clock += SEED_DURATION[t.type] * 1000;
    finishTask(p, t, clock);
  }
  if (stage === 'done') return;
  const t = p.tasks[stopAt];
  startTask(p, t, clock + 60_000);
  t.ticks = stage.ticks ?? 0;
  if (stage.status === 'RUNNING' && HUMAN.includes(t.type)) {
    t.status = 'RUNNING';
    t.plunet_job_status = 'IN_PROGRESS';
    emit(`${label(t.type)} started by ${t.assignee?.name} · Plunet job J-${t.plunet_job_id} → IN_PROGRESS`, { p, t, kind: 'STATE', actor: 'plunet', at: clock + 120_000 });
  }
  if (stage.status === 'FAILED') {
    p.qaWillFail = true;
    finishTask(p, t, clock + 70_000);
  }
  if (stage.paused) {
    p.paused = true;
    emit('Workflow paused', { p, kind: 'ACTION', actor: orderOf(p).pm.name, reason: 'Waiting for updated legal text from the customer', at: clock + 90_000 });
  }
}

function newOrder(fields: { kind: OrderKind; title: string; customer: Ref; pm: Ref; deadline: number | null; template: string; site: string; lang: string; destination?: Destination; createdAgo?: number }): MOrder {
  const isQuote = fields.kind === 'QUOTE';
  const o: MOrder = {
    id: ++ids.order,
    kind: fields.kind,
    number: isQuote ? `AN-${year}-${String(++ids.quoteNo).padStart(4, '0')}` : `AU-${year}-${String(++ids.orderNo).padStart(4, '0')}`,
    title: fields.title,
    customer: fields.customer,
    pm: fields.pm,
    deadline: fields.deadline,
    template: TEMPLATES.find((t) => t.code === fields.template) ?? TEMPLATES[0],
    default_destination: fields.destination ?? 'POLYLANG',
    destination_url: null,
    source_site: fields.site,
    source_lang: fields.lang,
    plunet_order_id: isQuote ? null : 97600 + ids.order,
    plunet_quote_id: isQuote ? 41200 + ids.order : null,
    created_at: now() - (fields.createdAgo ?? 0),
    rejected: false,
    accepted: null,
    positions: [],
  };
  orders.push(o);
  return o;
}

const post = (id: number) => POSTS.find((p) => p.id === id)!;
const cust = (id: number) => CUSTOMERS.find((c) => c.id === id)!;
const pm = (id: number) => RESOURCES.find((r) => r.id === id)!;

function seed(): void {
  const D = 24 * H;
  // Spring product pages: the order from the design, one failed QA.
  const a = newOrder({ kind: 'ORDER', title: 'Spring product pages', customer: cust(1), pm: pm(11), deadline: now() + 5 * D, template: 'standard', site: 'maison-lumiere.com', lang: 'en', createdAgo: 30 * H });
  emit('Order created in Plunet', { o: a, kind: 'ACTION', actor: 'Claire Dubois', at: a.created_at });
  const stagesA: [number, string, SeedStage, number][] = [
    [412, 'fr', 'done', 20 * H], [412, 'de-at', { at: 'REV', status: 'WAITING' }, 0.4 * H],
    [418, 'fr', 'done', 18 * H], [418, 'de-at', { at: 'TRA', status: 'RUNNING', ticks: 2 }, 0.2 * H],
    [433, 'fr', { at: 'QA', status: 'FAILED' }, 0.1 * H], [433, 'de-at', 'done', 2 * H],
  ];
  // Spring product pages: P06 passed QA before P05 failed.
  stagesA.forEach(([id, lang, stage, ago], i) => {
    const p = buildPosition(a, post(id), lang, i + 1, 'POLYLANG', null);
    if (id === 433 && lang === 'de-at') p.qaWillFail = false;
    a.positions.push(p);
    seedStage(p, stage, ago);
  });

  const b = newOrder({ kind: 'ORDER', title: 'Help center refresh', customer: cust(2), pm: pm(12), deadline: now() + 9 * D, template: 'standard', site: 'alpentech.at', lang: 'de-at', createdAgo: 20 * H });
  [[702, 'en', 'done', 3 * H], [702, 'fr', { at: 'TRA', status: 'RUNNING', ticks: 1 }, 0.3 * H], [705, 'en', { at: 'REV', status: 'WAITING' }, 0.5 * H], [705, 'fr', { at: 'TRA', status: 'WAITING' }, 0.4 * H]].forEach(([id, lang, stage, ago], i) => {
    const p = buildPosition(b, post(id as number), lang as string, i + 1, 'POLYLANG', null);
    b.positions.push(p);
    seedStage(p, stage as SeedStage, ago as number);
  });

  const c = newOrder({ kind: 'QUOTE', title: 'Careers section', customer: cust(3), pm: pm(11), deadline: now() + 13 * D, template: 'standard', site: 'maison-lumiere.com', lang: 'en', createdAgo: 2 * H });
  [[421, 'fr'], [440, 'fr'], [440, 'de-at']].forEach(([id, lang], i) => c.positions.push(buildPosition(c, post(id as number), lang as string, i + 1, 'POLYLANG', null)));
  emit('Quote created in Plunet and sent to the customer', { o: c, kind: 'ACTION', actor: 'Claire Dubois', at: c.created_at });

  const d = newOrder({ kind: 'ORDER', title: 'Privacy policy update', customer: cust(1), pm: pm(13), deadline: now() + 7 * D, template: 'regulated', site: 'maison-lumiere.com', lang: 'en', createdAgo: 10 * H });
  ['fr', 'de-at'].forEach((lang, i) => {
    const p = buildPosition(d, post(445), lang, i + 1, 'POLYLANG', null);
    d.positions.push(p);
    seedStage(p, { at: 'TRA', status: 'RUNNING', ticks: 1, paused: true }, H);
  });

  const e = newOrder({ kind: 'ORDER', title: 'Onboarding emails', customer: cust(2), pm: pm(13), deadline: now() - 1 * D, template: 'light', site: 'alpentech.at', lang: 'de-at', createdAgo: 4 * D });
  [[711, 'en', 'done'], [711, 'fr', 'done'], [712, 'en', 'done'], [712, 'fr', 'done'], [713, 'en', { at: 'TRA', status: 'WAITING' }]].forEach(([id, lang, stage], i) => {
    const p = buildPosition(e, post(id as number), lang as string, i + 1, 'POLYLANG', null);
    e.positions.push(p);
    seedStage(p, stage as SeedStage, (5 - i) * 6 * H);
  });

  const f = newOrder({ kind: 'ORDER', title: 'Product launch blog', customer: cust(4), pm: pm(12), deadline: now() + 1 * D, template: 'light', site: 'maison-lumiere.com', lang: 'en', createdAgo: 3 * D });
  [412, 418, 421, 440].flatMap((id) => ['fr', 'de-at'].map((lang) => [id, lang] as const)).forEach(([id, lang], i) => {
    const p = buildPosition(f, post(id), lang, i + 1, 'POLYLANG', null);
    f.positions.push(p);
    seedStage(p, 'done', 30 * H - i * H);
  });

  const g = newOrder({ kind: 'QUOTE', title: 'Annual report summary', customer: cust(4), pm: pm(11), deadline: now() - 10 * D, template: 'standard', site: 'maison-lumiere.com', lang: 'en', createdAgo: 9 * D });
  [[421, 'fr'], [421, 'it']].forEach(([id, lang], i) => g.positions.push(buildPosition(g, post(id as number), lang as string, i + 1, 'POLYLANG', null)));
  g.rejected = true;
  emit('Quote rejected in Plunet', { o: g, kind: 'STATE', actor: 'plunet', at: now() - 6 * D });

  events.sort((x, y) => x.created_at.localeCompare(y.created_at));
  events.forEach((ev, i) => (ev.id = i + 1));
  ids.event = events.length;
}

seed();
setInterval(tick, TICK_MS);

// ---------------------------------------------------------------- API

const delay = <T>(value: () => T): Promise<T> =>
  new Promise((resolve, reject) =>
    setTimeout(() => {
      try {
        resolve(structuredClone(value()));
      } catch (err) {
        reject(err);
      }
    }, LATENCY_MS),
  );

function findOrder(id: number): MOrder {
  const o = orders.find((x) => x.id === id);
  if (!o) throw new ApiError(404, `Order ${id} not found`);
  return o;
}

function findPosition(id: number): MPosition {
  for (const o of orders) for (const p of o.positions) if (p.id === id) return p;
  throw new ApiError(404, `Position ${id} not found`);
}

const actor = () => getActor() || 'you';

function applyAction(p: MPosition, a: WorkflowAction): void {
  const status = workflowStatus(p);
  const conflict = (msg: string) => new ApiError(409, msg);
  switch (a.action) {
    case 'pause':
      if (status !== 'RUNNING' && status !== 'WAITING') throw conflict(`Cannot pause a workflow that is ${status}`);
      p.paused = true;
      emit('Workflow paused. Tasks assigned to people continue in Plunet.', { p, kind: 'ACTION', actor: actor(), reason: a.reason });
      return;
    case 'resume':
      if (status !== 'PAUSED') throw conflict(`Cannot resume a workflow that is ${status}`);
      p.paused = false;
      emit('Workflow resumed', { p, kind: 'ACTION', actor: actor(), reason: a.reason });
      return;
    case 'retry': {
      const t = currentTask(p);
      if (!t || t.status !== 'FAILED') throw conflict('Retry is only possible on a failed task');
      emit(`Retry requested for ${label(t.type)}`, { p, t, kind: 'ACTION', actor: actor(), reason: a.reason });
      startTask(p, t);
      return;
    }
    case 'restart_from': {
      if (!['FAILED', 'PAUSED', 'COMPLETED'].includes(status)) throw conflict(`Cannot restart a workflow that is ${status}`);
      const from = p.tasks.find((t) => t.seq === a.task_seq);
      if (!from) throw conflict('Unknown task');
      for (const t of p.tasks.filter((x) => x.seq >= from.seq)) {
        t.status = 'PENDING';
        t.overlay = null;
        t.error = null;
        t.findings = null;
        t.finished_at = null;
        t.started_at = null;
        if (HUMAN.includes(t.type)) t.plunet_job_status = 'IN_PREPERATION';
      }
      if (from.type === 'TRA' || from.type === 'IMPORT') p.translated = false;
      p.paused = false;
      p.note = null;
      emit(`Restarted from ${label(from.type)}`, { p, t: from, kind: 'ACTION', actor: actor(), reason: a.reason });
      startTask(p, from);
      return;
    }
    case 'cancel':
      if (status === 'CANCELLED' || status === 'COMPLETED') throw conflict(`Cannot cancel a workflow that is ${status}`);
      if (!a.reason?.trim()) throw new ApiError(422, 'A reason is required to cancel');
      for (const t of p.tasks) {
        if (t.status === 'DONE' || t.status === 'SKIPPED') continue;
        t.status = 'CANCELLED';
        t.overlay = null;
        if (t.plunet_job_id) t.plunet_job_status = 'CANCELED';
      }
      p.cancelled = true;
      p.paused = false;
      emit('Workflow cancelled; open Plunet jobs set to CANCELED', { p, kind: 'ACTION', actor: actor(), reason: a.reason });
  }
}

function segments(p: MPosition): Segment[] {
  const qa = p.tasks.find((t) => t.type === 'QA');
  const findings = qa?.findings ?? [];
  return p.post.segments.map((source, i) => {
    const unit_id = `u-${String(i + 1).padStart(3, '0')}`;
    const unitFindings = findings.filter((f) => f.unit_id === unit_id);
    const broken = unitFindings.some((f) => f.code === 'PLACEHOLDER_MISMATCH');
    const target = !p.translated ? '' : `[${p.target_lang}] ${broken ? source.replace(PLACEHOLDER, '').replace(/\s+/g, ' ') : source}`;
    return { unit_id, source, target, findings: unitFindings };
  });
}

function analytics(groupBy: 'pm' | 'customer') {
  const rows = new Map<string, AnalyticsRow & { durations: number[] }>();
  for (const o of orders.filter((x) => x.kind === 'ORDER')) {
    const ref = groupBy === 'pm' ? o.pm : o.customer;
    const key = String(ref.id);
    const row = rows.get(key) ?? { key, label: ref.name, orders: 0, positions: 0, completed: 0, avg_duration_hours: null, cost: 0, errors: 0, durations: [] };
    row.orders += 1;
    for (const p of o.positions) {
      row.positions += 1;
      row.errors += p.tasks.reduce((n, t) => n + t.failures, 0);
      row.cost += p.tasks.reduce((n, t) => n + (t.cost ?? 0), 0);
      if (workflowStatus(p) === 'COMPLETED') {
        row.completed += 1;
        const start = p.tasks[0].started_at;
        const end = p.tasks[p.tasks.length - 1].finished_at;
        if (start && end) row.durations.push((end - start) / H);
      }
    }
    rows.set(key, row);
  }
  return {
    group_by: groupBy,
    currency: 'EUR',
    rows: [...rows.values()].map(({ durations, ...r }) => ({
      ...r,
      cost: Math.round(r.cost * 100) / 100,
      avg_duration_hours: durations.length ? Math.round((durations.reduce((a, b) => a + b, 0) / durations.length) * 10) / 10 : null,
    })),
  };
}

export const mockApi: Api = {
  mode: 'mock',
  listOrders: (f = {}) =>
    delay(() =>
      orders
        .map(summaryDto)
        .filter((o) => !f.kind || o.kind === f.kind)
        .filter((o) => !f.attention || o.status === 'NEEDS_ATTENTION' || o.overdue)
        .filter((o) => !f.pm_id || o.pm?.id === f.pm_id)
        .filter((o) => !f.customer_id || o.customer?.id === f.customer_id)
        .filter((o) => !f.q || `${o.number} ${o.title} ${o.customer?.name}`.toLowerCase().includes(f.q.toLowerCase()))
        .sort((x, y) => y.id - x.id),
    ),
  getOrder: (id) => delay(() => detailDto(findOrder(id))),
  createOrder: (req: CreateOrderRequest) =>
    delay(() => {
      if (!req.post_ids.length || !req.target_langs.length) throw new ApiError(422, 'Select at least one post and one target language');
      const o = newOrder({
        kind: req.kind, title: req.title || 'Untitled', customer: cust(req.customer_id), pm: pm(req.pm_resource_id),
        deadline: req.deadline ? Date.parse(req.deadline) : null, template: req.template_code, site: req.source_site, lang: req.source_lang, destination: req.destination,
      });
      o.destination_url = req.destination_url;
      let no = 0;
      for (const id of req.post_ids) for (const lang of req.target_langs) o.positions.push(buildPosition(o, post(id), lang, ++no, req.destination, req.destination_url));
      emit(req.kind === 'QUOTE' ? 'Quote created in Plunet' : `Order created in Plunet with ${no} items; workflows starting`, { o, kind: 'ACTION', actor: actor() });
      if (o.kind === 'ORDER') o.positions.forEach((p) => startTask(p, p.tasks[0]));
      return detailDto(o);
    }),
  acceptQuote: (id) =>
    delay(() => {
      const o = findOrder(id);
      if (o.kind !== 'QUOTE' || o.rejected || o.accepted !== null) throw new ApiError(409, 'Only an open quote can be accepted');
      o.accepted = 0;
      emit('Quote accepted; waiting for the PM to convert it into an order in Plunet', { o, kind: 'ACTION', actor: actor() });
      return detailDto(o);
    }),
  rejectQuote: (id) =>
    delay(() => {
      const o = findOrder(id);
      if (o.kind !== 'QUOTE' || o.rejected) throw new ApiError(409, 'Only an open quote can be rejected');
      o.accepted = null;
      o.rejected = true;
      emit('Quote rejected', { o, kind: 'ACTION', actor: actor() });
      return detailDto(o);
    }),
  orderAction: (id, action) =>
    delay(() => {
      const o = findOrder(id);
      for (const p of o.positions) {
        const s = workflowStatus(p);
        if (action === 'pause' && (s === 'RUNNING' || s === 'WAITING')) applyAction(p, { action: 'pause' });
        if (action === 'resume' && s === 'PAUSED') applyAction(p, { action: 'resume' });
        if (action === 'retry_failed' && s === 'FAILED') applyAction(p, { action: 'retry' });
      }
      return detailDto(o);
    }),
  getPosition: (id) => delay(() => positionDetailDto(findPosition(id))),
  workflowAction: (id, action) =>
    delay(() => {
      const p = findPosition(id);
      applyAction(p, action);
      return positionDetailDto(p);
    }),
  listEvents: (scope, limit = 500) =>
    delay(() =>
      events
        .filter((e) => (scope.order_id === undefined || e.order_id === scope.order_id) && (scope.position_id === undefined || e.position_id === scope.position_id))
        .slice(-limit),
    ),
  getSegments: (id) => delay(() => segments(findPosition(id))),
  listCustomers: () => delay(() => CUSTOMERS),
  listResources: () => delay(() => RESOURCES),
  listTemplates: () => delay(() => TEMPLATES),
  listSites: () => delay(() => SITES),
  listLanguages: () => delay(() => LANGUAGES),
  listPosts: (site, lang) =>
    delay(() =>
      POSTS.filter((p) => p.site === site && p.lang === lang).map((p) => ({ id: p.id, title: p.title, type: p.type, lang: p.lang, words: POST_WORDS[p.id] ?? 300, translations: p.translations })),
    ),
  analytics: (groupBy) => delay(() => analytics(groupBy)),
  subscribe(scope, onEvent) {
    const l: Listener = { scope, onEvent: (e) => onEvent(structuredClone(e)) };
    listeners.add(l);
    return () => listeners.delete(l);
  },
};
