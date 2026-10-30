import type { WorkflowStatus } from '../api';
import { wfTone } from './StatusTag';

/** One segment per position, coloured by workflow status. */
export function SegmentBar({ statuses, tall = false }: { statuses: WorkflowStatus[]; tall?: boolean }) {
  return (
    <span className={`segbar${tall ? ' segbar--tall' : ''}`} aria-hidden="true">
      {statuses.map((s, i) => (
        <span key={i} className={`segbar__seg tone-bg--${wfTone(s)}`} />
      ))}
    </span>
  );
}
