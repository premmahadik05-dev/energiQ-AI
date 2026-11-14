/** Client-side checks that mirror the backend rules (backend/app/security.py, services/data.py). The server stays the authority. */

export const EMAIL_RE = /^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,}$/;
const COMMON_PASSWORDS = new Set(['password123', '1234567890', 'qwertyuiop', 'password1234', 'letmein1234', 'admin12345']);

export function validateEmail(raw: string): string | null {
  const email = raw.trim();
  if (!email) return 'Enter your e-mail address.';
  if (email.length > 254 || !EMAIL_RE.test(email)) return 'Enter a valid e-mail address.';
  return null;
}

export function validatePassword(pw: string): string | null {
  if (pw.length < 10 || pw.length > 128) return 'Password must be 10-128 characters.';
  if (!(/[A-Za-z]/.test(pw) && /\d/.test(pw))) return 'Password must contain letters and digits.';
  if (COMMON_PASSWORDS.has(pw.toLowerCase()) || new Set(pw).size < 5) return 'Password is too easy to guess.';
  return null;
}

export function validateFullName(name: string): string | null {
  return name.length > 120 ? 'Name can be at most 120 characters.' : null;
}
