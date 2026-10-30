// API contract v2 (docs/backend-architecture.md §8).
// Both the mock (src/api/mock) and the HTTP client (src/api/http.ts) implement `Api`.

export type OrderKind = 'ORDER' | 'QUOTE';
export type OrderStatus =
  | 'DRAFT'
  | 'AWAITING_ACCEPTANCE'
  /** Quote accepted; waits for the PM to convert it into an order in Plunet. */
  | 'ACCEPTED'
  | 'REJECTED'
  | 'RUNNING'
  | 'NEEDS_ATTENTION'
  | 'COMPLETED'
  | 'CANCELLED';
export type WorkflowStatus =
  | 'NOT_STARTED'
  | 'RUNNING'
  | 'WAITING'
  | 'PAUSED'
  | 'FAILED'
  | 'CANCELLED'
  | 'COMPLETED';
export type TaskType = 'IMPORT' | 'PM' | 'TRA' | 'REV' | 'QA' | 'DELIVER';
export type TaskStatus = 'PENDING' | 'WAITING' | 'RUNNING' | 'DONE' | 'FAILED' | 'SKIPPED' | 'CANCELLED';
export type Overlay = 'FAILED' | 'PAUSED' | null;
export type Destination = 'POLYLANG' | 'ENDPOINT' | 'NONE';
export type EventKind = 'LOG' | 'STATE' | 'ACTION';
export type EventLevel = 'INFO' | 'WARN' | 'ERROR';

export interface Ref {
  id: number;
  name: string;
}

export interface OrderProgress {
  total: number;
  /** One entry per position, in position order (drives the segmented progress bar). */
  statuses: WorkflowStatus[];
}

export interface OrderSummary {
  id: number;
  kind: OrderKind;
  status: OrderStatus;
  number: string | null;
  title: string;
  customer: Ref | null;
  pm: Ref | null;
  deadline: string | null;
  overdue: boolean;
  progress: OrderProgress;
  last_activity: { message: string; at: string } | null;
}

export interface QaFinding {
  code: string;
  level: 'BLOCKING' | 'WARNING';
  unit_id: string;
  message: string;
}

export interface Task {
  id: number;
  seq: number;
  type: TaskType;
  status: TaskStatus;
  overlay: Overlay;
  plunet_job_id: number | null;
  plunet_job_status: string | null;
  assignee: Ref | null;
  attempts: number;
  cost: number | null;
  currency: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  error: string | null;
  findings: QaFinding[] | null;
}

export interface Position {
  id: number;
  order_id: number;
  no: number;
  title: string;
  polylang_post_id: number | null;
  source_lang: string;
  target_lang: string;
  plunet_item_id: number | null;
  file_name: string;
  words: number;
  segments: number;
  destination: Destination;
  destination_url: string | null;
  status: WorkflowStatus;
  note: string | null;
  tasks: Task[];
}

export interface OrderDetail extends OrderSummary {
  template: { code: string; name: string };
  default_destination: Destination;
  destination_url: string | null;
  source_site: string | null;
  source_lang: string;
  plunet_order_id: number | null;
  plunet_quote_id: number | null;
  created_at: string;
  positions: Position[];
  totals: { words: number; cost: number | null; currency: string | null; errors: number; elapsed_seconds: number };
}

export interface PositionDetail {
  order: Pick<OrderDetail, 'id' | 'number' | 'title' | 'kind' | 'template'>;
  position: Position;
}

export interface EventItem {
  id: number;
  created_at: string;
  kind: EventKind;
  level: EventLevel;
  order_id: number | null;
  position_id: number | null;
  task_id: number | null;
  actor: string;
  message: string;
  reason: string | null;
  data: Record<string, unknown> | null;
}

export interface Segment {
  unit_id: string;
  source: string;
  target: string;
  findings: QaFinding[];
}

export interface Template {
  code: string;
  name: string;
  tasks: TaskType[];
}

export interface Language {
  slug: string;
  name: string;
  locale: string;
}

export interface SourcePost {
  id: number;
  title: string;
  type: 'post' | 'page';
  lang: string;
  words: number;
  translations: Record<string, number>;
}

export interface OrderFilters {
  kind?: OrderKind;
  attention?: boolean;
  pm_id?: number;
  customer_id?: number;
  q?: string;
}

export interface CreateOrderRequest {
  kind: OrderKind;
  title: string;
  customer_id: number;
  pm_resource_id: number;
  deadline: string | null;
  source_site: string;
  source_lang: string;
  post_ids: number[];
  target_langs: string[];
  template_code: string;
  destination: Destination;
  destination_url: string | null;
}

export type WorkflowActionName = 'pause' | 'resume' | 'retry' | 'restart_from' | 'cancel';
export interface WorkflowAction {
  action: WorkflowActionName;
  task_seq?: number;
  reason?: string;
}
export type OrderActionName = 'pause' | 'resume' | 'retry_failed';

export interface AnalyticsRow {
  key: string;
  label: string;
  orders: number;
  positions: number;
  completed: number;
  avg_duration_hours: number | null;
  cost: number;
  errors: number;
}
export interface AnalyticsSummary {
  group_by: 'pm' | 'customer';
  currency: string;
  rows: AnalyticsRow[];
}

export interface EventScope {
  order_id?: number;
  position_id?: number;
}

export interface Api {
  readonly mode: 'mock' | 'http';
  listOrders(filters?: OrderFilters): Promise<OrderSummary[]>;
  getOrder(id: number): Promise<OrderDetail>;
  createOrder(req: CreateOrderRequest): Promise<OrderDetail>;
  acceptQuote(id: number): Promise<OrderDetail>;
  rejectQuote(id: number): Promise<OrderDetail>;
  orderAction(id: number, action: OrderActionName): Promise<OrderDetail>;
  getPosition(id: number): Promise<PositionDetail>;
  workflowAction(positionId: number, action: WorkflowAction): Promise<PositionDetail>;
  listEvents(scope: EventScope, limit?: number): Promise<EventItem[]>;
  getSegments(positionId: number): Promise<Segment[]>;
  listCustomers(): Promise<Ref[]>;
  listResources(): Promise<Ref[]>;
  listTemplates(): Promise<Template[]>;
  listSites(): Promise<string[]>;
  listLanguages(site: string): Promise<Language[]>;
  listPosts(site: string, lang: string): Promise<SourcePost[]>;
  analytics(groupBy: 'pm' | 'customer'): Promise<AnalyticsSummary>;
  /** Live events (SSE in http mode). Calls `onResync` when events may have been missed. */
  subscribe(scope: EventScope, onEvent: (e: EventItem) => void, onResync?: () => void): () => void;
}

/** The order number from Plunet, or the FOX MLO id until Plunet has created the order. */
export function orderLabel(o: { id: number; number: string | null }): string {
  return o.number ?? `#${o.id}`;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
