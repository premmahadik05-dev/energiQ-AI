/**
 * Notification links come from the API and the post-login return path comes from the URL; only app-internal paths are
 * followed. Backslashes are refused too: browsers read "/\host" as "//host", the open-redirect bypass that the
 * react-router 6 advisory (GHSA-wrjc-x8rr-h8h6) describes.
 */
export function safeInternalLink(link: string): string | null {
  return link.startsWith('/') && !link.startsWith('//') && !link.includes('\\') ? link : null;
}
