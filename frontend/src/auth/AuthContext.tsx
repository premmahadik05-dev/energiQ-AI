import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { configureApi } from '../api/client';
import { authApi } from '../api/endpoints';
import type { Role, User } from '../api/types';
import { clearToken, getToken, setToken } from './tokenStore';

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous';

export interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  /** true when the last sign-out was caused by a 401 (expired or revoked token) */
  sessionExpired: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (email: string, password: string, fullName: string) => Promise<User>;
  logout: () => void;
  hasRole: (...roles: Role[]) => boolean;
  /** analyst and admin may change data; viewers are read-only (the server is still the authority) */
  canWrite: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>(() => (getToken() ? 'loading' : 'anonymous'));
  const [user, setUser] = useState<User | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const statusRef = useRef(status);
  statusRef.current = status;

  const drop = useCallback((expired: boolean) => {
    clearToken();
    setUser(null);
    setStatus('anonymous');
    setSessionExpired(expired);
  }, []);

  useEffect(() => {
    configureApi({
      getToken,
      onUnauthorized: () => {
        if (statusRef.current !== 'anonymous') drop(true);
      },
    });
  }, [drop]);

  useEffect(() => {
    if (!getToken()) return;
    const ctl = new AbortController();
    authApi.me({ signal: ctl.signal }).then(
      (u) => {
        setUser(u);
        setStatus('authenticated');
      },
      () => {
        if (!ctl.signal.aborted) drop(false);
      },
    );
    return () => ctl.abort();
  }, [drop]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi.login(email.trim(), password);
    setToken(res.access_token);
    setUser(res.user);
    setSessionExpired(false);
    setStatus('authenticated');
    return res.user;
  }, []);

  const register = useCallback(
    async (email: string, password: string, fullName: string) => {
      await authApi.register(email.trim(), password, fullName.trim());
      return login(email, password);
    },
    [login],
  );

  const logout = useCallback(() => drop(false), [drop]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      sessionExpired,
      login,
      register,
      logout,
      hasRole: (...roles) => !!user && roles.includes(user.role),
      canWrite: !!user && (user.role === 'admin' || user.role === 'analyst'),
    }),
    [status, user, sessionExpired, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
