import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { AuthShell } from '../components/auth/AuthShell';
import { PasswordField, PasswordRules } from '../components/auth/AuthFields';
import { Notice, Spinner } from '../components/ui/feedback';
import { CheckboxField, TextField } from '../components/ui/forms';
import { Icon } from '../components/ui/Icon';
import { safeInternalLink } from '../lib/links';
import { KEYS, storageGet, storageRemove, storageSet } from '../lib/storage';
import { validateEmail, validateFullName, validatePassword } from '../lib/validation';

function usePageTitle(title: string) {
  useEffect(() => {
    const before = document.title;
    document.title = `${title} · EnergiQ AI`;
    return () => {
      document.title = before;
    };
  }, [title]);
}

function Heading({ title, children }: { title: string; children: string }) {
  return (
    <div className="mb-7">
      <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.025em]">{title}</h1>
      <p className="mt-2 text-[15px] leading-relaxed text-muted">{children}</p>
    </div>
  );
}

/** Field errors appear once a field has been left (or the form was submitted), then follow the input while it is edited. */
function useTouched<K extends string>(keys: readonly K[]) {
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  return {
    touched: (k: K) => touched[k] === true,
    touch: (k: K) => setTouched((t) => ({ ...t, [k]: true })),
    touchAll: () => setTouched(Object.fromEntries(keys.map((k) => [k, true]))),
  };
}

function focusFirstInvalid(form: HTMLFormElement | null) {
  requestAnimationFrame(() => form?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus());
}

function SubmitButton({ busy, idle, working }: { busy: boolean; idle: string; working: string }) {
  return (
    <button type="submit" className="btn-primary btn-lg w-full" disabled={busy}>
      {busy && <Spinner className="h-[18px] w-[18px]" />}
      {busy ? working : idle}
    </button>
  );
}

export function LoginPage() {
  usePageTitle('Sign in');
  const { login, sessionExpired } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const formRef = useRef<HTMLFormElement>(null);
  const [saved] = useState(() => storageGet('local', KEYS.rememberedEmail) ?? '');
  const [email, setEmail] = useState(saved);
  const [remember, setRemember] = useState(saved !== '');
  const [password, setPassword] = useState('');
  const [serverError, setServerError] = useState<string | null>(null);
  const [showForgot, setShowForgot] = useState(false);
  const [busy, setBusy] = useState(false);
  const { touched, touch, touchAll } = useTouched(['email', 'password'] as const);

  const errors = {
    email: touched('email') ? validateEmail(email) : null,
    password: touched('password') && !password ? 'Enter your password.' : null,
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    touchAll();
    if (validateEmail(email) || !password) {
      setServerError(null); // an old "wrong password" message would otherwise sit beside the new validation message
      focusFirstInvalid(formRef.current);
      return;
    }
    setBusy(true);
    setServerError(null);
    try {
      await login(email, password);
      if (remember) storageSet('local', KEYS.rememberedEmail, email.trim());
      else storageRemove('local', KEYS.rememberedEmail);
      nav((from && safeInternalLink(from)) || '/', { replace: true });
    } catch (err) {
      setServerError(err instanceof ApiError || err instanceof Error ? err.message : 'Sign-in failed.');
      setBusy(false);
    }
  };

  return (
    <AuthShell
      footer={
        <>
          New to EnergiQ AI?{' '}
          <Link to="/register" className="font-semibold text-accent underline-offset-2 hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <Heading title="Welcome back">Sign in to continue to your energy intelligence workspace.</Heading>
      <form ref={formRef} onSubmit={submit} noValidate aria-busy={busy} className="space-y-5">
        {sessionExpired && (
          <Notice tone="warn" role="status" title="Your session ended">
            Sign in again to continue.
          </Notice>
        )}
        {serverError && <Notice tone="error" role="alert">{serverError}</Notice>}
        <TextField
          label="Email address"
          type="email"
          autoComplete="username"
          inputMode="email"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            setServerError(null);
          }}
          onBlur={() => email && touch('email')}
          error={errors.email}
          inputClassName="min-h-[44px]"
          leading={<Icon name="mail" className="h-[18px] w-[18px]" />}
          placeholder="you@example.com"
        />
        <PasswordField
          label="Password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            setServerError(null);
          }}
          onBlur={() => password && touch('password')}
          error={errors.password}
          labelAside={
            <button type="button" onClick={() => setShowForgot((v) => !v)} aria-expanded={showForgot} aria-controls="forgot-help" className="text-[13px] font-medium text-accent underline-offset-2 hover:underline">
              Forgot password?
            </button>
          }
        />
        {showForgot && (
          <div id="forgot-help">
            <Notice tone="info" title="Password reset is not available yet">
              This version has no reset by e-mail. If you are locked out, ask the person who manages this installation, or create a new account with another e-mail address.
            </Notice>
          </div>
        )}
        <CheckboxField label="Remember my e-mail on this device" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
        <SubmitButton busy={busy} idle="Sign in" working="Signing in…" />
      </form>
    </AuthShell>
  );
}

export function RegisterPage() {
  usePageTitle('Create account');
  const { register } = useAuth();
  const nav = useNavigate();
  const formRef = useRef<HTMLFormElement>(null);
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { touched, touch, touchAll } = useTouched(['fullName', 'email', 'password', 'confirm'] as const);

  const confirmError = !confirm ? 'Confirm your password.' : confirm !== password ? 'Passwords do not match.' : null;
  const errors = {
    fullName: touched('fullName') ? validateFullName(fullName) : null,
    email: touched('email') ? validateEmail(email) : null,
    password: touched('password') ? validatePassword(password) : null,
    confirm: touched('confirm') ? confirmError : null,
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    touchAll();
    if (validateFullName(fullName) || validateEmail(email) || validatePassword(password) || confirmError) {
      focusFirstInvalid(formRef.current);
      return;
    }
    setBusy(true);
    setServerError(null);
    try {
      await register(email, password, fullName);
      nav('/', { replace: true, state: { welcome: true } });
    } catch (err) {
      setServerError(err instanceof Error ? err.message : 'Registration failed.');
      setBusy(false);
    }
  };

  return (
    <AuthShell
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-semibold text-accent underline-offset-2 hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <Heading title="Create your account">Start forecasting and managing your society's electricity use.</Heading>
      <form ref={formRef} onSubmit={submit} noValidate aria-busy={busy} className="space-y-5">
        {serverError && <Notice tone="error" role="alert">{serverError}</Notice>}
        <TextField
          label="Full name (optional)"
          autoComplete="name"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          onBlur={() => fullName && touch('fullName')}
          error={errors.fullName}
          maxLength={120}
          inputClassName="min-h-[44px]"
          leading={<Icon name="user" className="h-[18px] w-[18px]" />}
        />
        <TextField
          label="Email address"
          type="email"
          autoComplete="username"
          inputMode="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onBlur={() => email && touch('email')}
          error={errors.email}
          inputClassName="min-h-[44px]"
          leading={<Icon name="mail" className="h-[18px] w-[18px]" />}
          placeholder="you@example.com"
        />
        <PasswordField label="Password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} onBlur={() => password && touch('password')} error={errors.password} hint={<PasswordRules value={password} />} />
        <PasswordField label="Confirm password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} onBlur={() => confirm && touch('confirm')} error={errors.confirm} />
        <SubmitButton busy={busy} idle="Create account" working="Creating account…" />
        <p className="text-center text-[12.5px] leading-relaxed text-muted">New accounts get the analyst role: they can acknowledge alerts and create reports.</p>
      </form>
    </AuthShell>
  );
}
