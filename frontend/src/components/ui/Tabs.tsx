import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react';

export interface TabDef<T extends string> {
  id: T;
  label: string;
}

/** WAI-ARIA tabs: arrow keys, Home and End move between tabs; the panel is labelled by its tab. */
export function Tabs<T extends string>({ tabs, value, onChange, label, children }: { tabs: TabDef<T>[]; value: T; onChange: (v: T) => void; label: string; children: ReactNode }) {
  const base = useId();
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const onKey = (e: KeyboardEvent) => {
    const i = tabs.findIndex((t) => t.id === value);
    let next = i;
    if (e.key === 'ArrowRight') next = (i + 1) % tabs.length;
    else if (e.key === 'ArrowLeft') next = (i - 1 + tabs.length) % tabs.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = tabs.length - 1;
    else return;
    e.preventDefault();
    const t = tabs[next];
    if (t) {
      onChange(t.id);
      refs.current[t.id]?.focus();
    }
  };
  return (
    <div>
      <div role="tablist" aria-label={label} onKeyDown={onKey} className="mb-4 flex gap-1 overflow-x-auto border-b border-line">
        {tabs.map((t) => (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[t.id] = el;
            }}
            role="tab"
            type="button"
            id={`${base}-tab-${t.id}`}
            aria-selected={value === t.id}
            aria-controls={`${base}-panel`}
            tabIndex={value === t.id ? 0 : -1}
            onClick={() => onChange(t.id)}
            className={`-mb-px whitespace-nowrap border-b-2 px-4 py-2 text-sm font-medium ${value === t.id ? 'border-accent text-ink' : 'border-transparent text-ink-2 hover:text-ink'}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${base}-panel`} aria-labelledby={`${base}-tab-${value}`}>
        {children}
      </div>
    </div>
  );
}
