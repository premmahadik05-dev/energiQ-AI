import { useId, useState, type InputHTMLAttributes, type ReactNode } from 'react';
import { TextField } from '../ui/forms';
import { Icon } from '../ui/Icon';

/** Password input with a lock icon and a show/hide button. The button never submits the form and keeps the keyboard focus where it is useful. */
export function PasswordField({ label, error, hint, labelAside, ...rest }: { label: string; error?: string | null; hint?: ReactNode; labelAside?: ReactNode } & Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>) {
  const [visible, setVisible] = useState(false);
  const word = label.toLowerCase();
  return (
    <TextField
      label={label}
      error={error}
      hint={hint}
      labelAside={labelAside}
      type={visible ? 'text' : 'password'}
      inputClassName="min-h-[44px]"
      leading={<Icon name="lock" className="h-[18px] w-[18px]" />}
      trailing={
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={`${visible ? 'Hide' : 'Show'} ${word}`}
          aria-pressed={visible}
          className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted transition-colors hover:bg-sunken hover:text-ink"
        >
          <Icon name={visible ? 'eyeOff' : 'eye'} className="h-[18px] w-[18px]" />
        </button>
      }
      {...rest}
    />
  );
}

/** Live checklist of the password rules the server enforces (length and a mix of letters and digits). */
export function PasswordRules({ value }: { value: string }) {
  const id = useId();
  const rules = [
    { ok: value.length >= 10 && value.length <= 128, text: '10 to 128 characters' },
    { ok: /[A-Za-z]/.test(value) && /\d/.test(value), text: 'At least one letter and one digit' },
  ];
  return (
    <ul aria-label="Password requirements" id={id} className="mt-1.5 space-y-1">
      {rules.map((r) => (
        <li key={r.text} className={`flex items-center gap-2 text-[12.5px] transition-colors ${r.ok ? 'text-accent' : 'text-muted'}`}>
          <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors ${r.ok ? 'border-accent bg-accent text-accent-ink' : 'border-line-strong'}`} aria-hidden="true">
            {r.ok && <Icon name="check" className="h-3 w-3" />}
          </span>
          <span>{r.text}</span>
          <span className="sr-only">{r.ok ? ': met' : ': not met'}</span>
        </li>
      ))}
    </ul>
  );
}
