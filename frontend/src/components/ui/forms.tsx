import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from 'react';

interface FieldShell {
  label: string;
  hint?: ReactNode;
  error?: string | null;
}

export function TextField({ label, hint, error, className = '', ...rest }: FieldShell & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-err` : null].filter(Boolean).join(' ') || undefined;
  return (
    <div className={className}>
      <label htmlFor={id} className="label">
        {label}
      </label>
      <input id={id} className={`input ${error ? 'border-bad' : ''}`} aria-invalid={error ? true : undefined} aria-describedby={describedBy} {...rest} />
      {hint && (
        <p id={`${id}-hint`} className="hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-err`} className="mt-1 text-xs font-medium text-bad">
          {error}
        </p>
      )}
    </div>
  );
}

export function SelectField({ label, hint, error, className = '', children, ...rest }: FieldShell & SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId();
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-err` : null].filter(Boolean).join(' ') || undefined;
  return (
    <div className={className}>
      <label htmlFor={id} className="label">
        {label}
      </label>
      <select id={id} className={`input pr-8 ${error ? 'border-bad' : ''}`} aria-invalid={error ? true : undefined} aria-describedby={describedBy} {...rest}>
        {children}
      </select>
      {hint && (
        <p id={`${id}-hint`} className="hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-err`} className="mt-1 text-xs font-medium text-bad">
          {error}
        </p>
      )}
    </div>
  );
}

export function CheckboxField({ label, hint, className = '', ...rest }: Omit<FieldShell, 'error'> & Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>) {
  const id = useId();
  return (
    <div className={className}>
      <div className="flex items-start gap-2">
        <input id={id} type="checkbox" className="mt-1 h-4 w-4 accent-[var(--accent)]" aria-describedby={hint ? `${id}-hint` : undefined} {...rest} />
        <label htmlFor={id} className="text-sm">
          {label}
        </label>
      </div>
      {hint && (
        <p id={`${id}-hint`} className="hint ml-6">
          {hint}
        </p>
      )}
    </div>
  );
}

/** Radio-group styled as a segmented control (keyboard: arrow keys move the selection, native radio behaviour). */
export function Segmented<T extends string>({ label, value, options, onChange, hideLabel = true }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; hideLabel?: boolean }) {
  const name = useId();
  return (
    <fieldset className="min-w-0">
      <legend className={hideLabel ? 'sr-only' : 'label'}>{label}</legend>
      <div className="inline-flex rounded border border-line-strong bg-sunken p-0.5">
        {options.map((o) => (
          <label
            key={o.value}
            className={`cursor-pointer rounded-[4px] px-3 py-1 text-sm font-medium has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent ${
              value === o.value ? 'bg-surface text-ink shadow-sm ring-1 ring-line' : 'text-ink-2 hover:text-ink'
            }`}
          >
            <input type="radio" className="sr-only" name={name} value={o.value} checked={value === o.value} onChange={() => onChange(o.value)} />
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
