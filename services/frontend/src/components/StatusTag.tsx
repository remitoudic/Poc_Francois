import type { ReactNode } from 'react';
import type { OrderStatus, TaskStatus, WorkflowStatus } from '../api';
import { useI18n } from '../i18n';

export type Tone = 'run' | 'wait' | 'fail' | 'pause' | 'done' | 'muted';

const WF_TONE: Record<WorkflowStatus, Tone> = {
  NOT_STARTED: 'muted', RUNNING: 'run', WAITING: 'wait', PAUSED: 'pause', FAILED: 'fail', CANCELLED: 'muted', COMPLETED: 'done',
};
const ORDER_TONE: Record<OrderStatus, Tone> = {
  DRAFT: 'muted', AWAITING_ACCEPTANCE: 'muted', ACCEPTED: 'wait', REJECTED: 'muted', RUNNING: 'run', NEEDS_ATTENTION: 'fail', COMPLETED: 'done', CANCELLED: 'muted',
};
export const TASK_TONE: Record<TaskStatus, Tone> = {
  PENDING: 'muted', WAITING: 'wait', RUNNING: 'run', DONE: 'done', FAILED: 'fail', SKIPPED: 'muted', CANCELLED: 'muted',
};
export const wfTone = (s: WorkflowStatus) => WF_TONE[s];

export function Tag({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`tag tag--${tone}`}>{children}</span>;
}

export function WorkflowTag({ status }: { status: WorkflowStatus }) {
  const { t } = useI18n();
  return <Tag tone={WF_TONE[status]}>{t(`wf.${status}`)}</Tag>;
}

export function OrderTag({ status }: { status: OrderStatus }) {
  const { t } = useI18n();
  return <Tag tone={ORDER_TONE[status]}>{t(`orderStatus.${status}`)}</Tag>;
}

export function KindTag({ kind }: { kind: 'ORDER' | 'QUOTE' }) {
  const { t } = useI18n();
  return (
    <span className={`kind kind--${kind.toLowerCase()}`} title={t(`kind.${kind}.plunet`)}>
      {t(`kind.${kind}`)}
    </span>
  );
}
