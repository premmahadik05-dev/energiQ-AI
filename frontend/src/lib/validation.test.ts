import { describe, expect, it } from 'vitest';
import { validateEmail, validateFullName, validatePassword } from './validation';

describe('e-mail and password rules (mirror the backend)', () => {
  it('accepts normal addresses and rejects malformed ones', () => {
    expect(validateEmail('ana@example.com')).toBeNull();
    expect(validateEmail('  ana@example.com  ')).toBeNull();
    expect(validateEmail('')).toMatch(/Enter your e-mail/);
    for (const bad of ['not-an-email', 'a@b', 'a b@example.com', '@example.com', 'a@@example.com']) expect(validateEmail(bad)).toBe('Enter a valid e-mail address.');
  });

  it('requires 10-128 characters with letters and digits', () => {
    expect(validatePassword('short1')).toMatch(/10-128/);
    expect(validatePassword('x'.repeat(129) + '1')).toMatch(/10-128/);
    expect(validatePassword('onlyletterspassword')).toMatch(/letters and digits/);
    expect(validatePassword('1234567890123')).toMatch(/letters and digits/);
    expect(validatePassword('Tester-Pass-2026')).toBeNull();
  });

  it('rejects common and low-variety passwords the backend would refuse', () => {
    expect(validatePassword('password1234')).toMatch(/too easy/);
    expect(validatePassword('aaaaaaaaa1')).toMatch(/too easy/); // fewer than 5 distinct characters
  });

  it('limits the display name to 120 characters', () => {
    expect(validateFullName('x'.repeat(120))).toBeNull();
    expect(validateFullName('x'.repeat(121))).toMatch(/120/);
  });
});
