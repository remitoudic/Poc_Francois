import type { ReactNode } from 'react';
import type { Tone } from './StatusTag';

export function Kpi({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: string; tone?: Tone }) {
  return (
    <div className="kpi">
      <span className="label">{label}</span>
      <span className={`kpi__value${tone ? ` tone-fg--${tone}` : ''}`}>{value}</span>
      {sub && <span className="kpi__sub">{sub}</span>}
    </div>
  );
}
