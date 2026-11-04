import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { Notice } from '../components/ui/feedback';
import { TextField } from '../components/ui/forms';
import { Logo } from '../components/ui/Icon';
import { Spinner } from '../components/ui/feedback';
import { safeInternalLink } from '../lib/links';
import { validateEmail, validateFullName, validatePassword } from '../lib/validation';

function AuthLayout({ title, children, footer }: { title: string; children: React.ReactNode; footer: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3">
          <Logo className="h-9 w-9" />
          <div>
            <p className="text-lg font-semibold leading-tight">EnergiQ AI</p>
            <p className="text-sm text-ink-2">Energy forecasting, anomaly detection and optimisation</p>
          </div>
        </div>
        <div className="card p-6">
          <h1 className="mb-4 text-xl">{title}</h1>
          {children}
        </div>
        <p className="mt-4 text-center text-sm text-ink-2">{footer}</p>
      </div>
    </div>
  );
}

export function LoginPage() {
  const { login, sessionExpired } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const next = { email: validateEmail(email) ?? undefined, password: password ? undefined : 'Enter your password.' };
    setErrors(next);
    if (next.email || next.password) return;
    setBusy(true);
    setServerError(null);
    try {
      await login(email, password);
      nav((from && safeInternalLink(from)) || '/', { replace: true });
    } catch (err) {
      setServerError(err instanceof ApiError || err instanceof Error ? err.message : 'Sign-in failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title="Sign in"
      footer={
        <>
          New here?{' '}
          <Link to="/register" className="text-accent underline">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={submit} noValidate className="space-y-4">
        {sessionExpired && <Notice tone="warn" role="status" title="Your session ended">Sign in again to continue.</Notice>}
        {serverError && <Notice tone="error" role="alert">{serverError}</Notice>}
        <TextField label="E-mail" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} />
        <TextField label="Password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} error={errors.password} />
        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {busy && <Spinner />}Sign in
        </button>
      </form>
    </AuthLayout>
  );
}

export function RegisterPage() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ fullName?: string; email?: string; password?: string }>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const next = { fullName: validateFullName(fullName) ?? undefined, email: validateEmail(email) ?? undefined, password: validatePassword(password) ?? undefined };
    setErrors(next);
    if (next.fullName || next.email || next.password) return;
    setBusy(true);
    setServerError(null);
    try {
      await register(email, password, fullName);
      nav('/', { replace: true });
    } catch (err) {
      setServerError(err instanceof Error ? err.message : 'Registration failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title="Create an account"
      footer={
        <>
          Already registered?{' '}
          <Link to="/login" className="text-accent underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={submit} noValidate className="space-y-4">
        {serverError && <Notice tone="error" role="alert">{serverError}</Notice>}
        <TextField label="Full name (optional)" autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} error={errors.fullName} maxLength={120} />
        <TextField label="E-mail" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} />
        <TextField label="Password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} error={errors.password} hint="10-128 characters, with letters and digits." />
        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {busy && <Spinner />}Create account
        </button>
        <p className="hint">New accounts get the analyst role: they can upload data, train models and run detections.</p>
      </form>
    </AuthLayout>
  );
}
