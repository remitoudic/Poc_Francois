import type { Task } from '../api';
import { useI18n } from '../i18n';
import { TASK_TONE } from './StatusTag';

/** Compact task chain: IMP → PM → TRA → REV → QA → DEL, coloured by task state. */
export function TaskChips({ tasks }: { tasks: Task[] }) {
  const { t } = useI18n();
  return (
    <span className="chips">
      {tasks.map((task) => {
        const tone = task.overlay === 'PAUSED' ? 'pause' : TASK_TONE[task.status];
        const title = `${t(`task.${task.type}`)} · ${t(`taskStatus.${task.status}`)}`;
        return (
          <span key={task.id} className={`chip chip--${tone}`} title={title} aria-label={title}>
            {t(`taskShort.${task.type}`)}
          </span>
        );
      })}
    </span>
  );
}
