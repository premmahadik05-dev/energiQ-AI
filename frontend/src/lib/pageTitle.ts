const BASE = 'EnergiQ AI';

/** Browser-tab title for each route, so tabs, history and screen readers say which page is open. */
const TITLES: Record<string, string> = {
  '/': 'Society overview',
  '/compare': 'Compare communities',
  '/consumption': 'Consumption',
  '/forecasting': 'Forecasting',
  '/buildings': 'Buildings',
  '/facilities': 'Common facilities',
  '/cost': 'Cost and peaks',
  '/alerts': 'Alerts',
  '/recommendations': 'Recommendations',
  '/reports': 'Reports',
  '/data-sources': 'Data sources',
  '/notifications': 'Notifications',
  '/jobs': 'Jobs',
  '/admin': 'Admin',
  '/society-admin': 'Society admin',
};

export function pageTitle(pathname: string): string {
  const key = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
  const t = TITLES[key];
  return t ? `${t} · ${BASE}` : `Page not found · ${BASE}`;
}
