import { useEffect, useId, useRef, type ReactNode } from 'react';

interface Props {
  title: string;
  children: ReactNode;
  footer: ReactNode;
  onClose: () => void;
}

/** Modal dialog built on <dialog>: focus trap, Esc to close, backdrop. */
export function Dialog({ title, children, footer, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const el = ref.current;
    if (el && !el.open) el.showModal();
    return () => el?.close();
  }, []);

  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <div className="dialog__body">
        <h2 id={titleId} className="dialog__title">{title}</h2>
        {children}
      </div>
      <div className="dialog__footer">{footer}</div>
    </dialog>
  );
}
