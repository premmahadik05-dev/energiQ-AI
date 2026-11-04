import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ChartFrame, type LegendItem } from './charts/ChartFrame';
import { ErrorBoundary } from './ErrorBoundary';
import { fx } from '../test/fixtures';
import { renderApp } from '../test/harness';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.documentElement.removeAttribute('data-theme');
});

const legend2: LegendItem[] = [
  { label: 'Actual load (kW)', color: 'var(--s1)', kind: 'line' },
  { label: 'Forecast (kW)', color: 'var(--s2)', kind: 'dash' },
];

describe('ChartFrame (every chart has a legend for 2+ series and a table alternative)', () => {
  it('shows the legend for two series and switches to the table view with the same numbers', async () => {
    render(
      <ChartFrame title="Load" summary="Two series over four days." legend={legend2} table={<table><caption>values</caption><tbody><tr><td>1.36</td></tr></tbody></table>}>
        <svg data-testid="plot" />
      </ChartFrame>,
    );
    expect(screen.getByRole('list', { name: 'Chart legend' })).toHaveTextContent('Forecast (kW)');
    expect(screen.getByTestId('plot')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Two series over four days.' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'Table' }));
    expect(screen.getByText('1.36')).toBeInTheDocument();
    expect(screen.queryByTestId('plot')).not.toBeInTheDocument();
  });

  it('omits the legend box for a single series (the title names it)', () => {
    render(
      <ChartFrame title="Load" summary="One series." legend={[legend2[0] as LegendItem]} table={<p>t</p>}>
        <svg />
      </ChartFrame>,
    );
    expect(screen.queryByRole('list', { name: 'Chart legend' })).not.toBeInTheDocument();
  });
});

describe('ErrorBoundary', () => {
  it('replaces a crashing page with a message and a way out instead of a blank screen', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    function Boom(): never {
      throw new Error('chart data was malformed');
    }
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong on this page');
    expect(screen.getByRole('alert')).toHaveTextContent('chart data was malformed');
    expect(screen.getByRole('link', { name: 'Go to the dashboard' })).toHaveAttribute('href', '/');
  });
});

describe('escaping and storage decisions', () => {
  it('renders API text as text: markup in a notification message is shown, never executed', async () => {
    const evil = '<img src=x onerror="window.__pwned = true"> 5 high severity';
    renderApp('/notifications', { routes: [{ path: '/api/v1/notifications', reply: [{ ...fx.notifications[0], message: evil }] }] });
    expect(await screen.findByText(evil)).toBeInTheDocument();
    expect(document.querySelector('img[src="x"]')).toBeNull();
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
  });

  it('does not follow notification links that leave the app', async () => {
    renderApp('/notifications', { routes: [{ path: '/api/v1/notifications', reply: [{ ...fx.notifications[0], link: 'https://evil.example/phish' }] }] });
    await screen.findByText(fx.notifications[0]?.message as string);
    expect(screen.queryByRole('link', { name: 'Open' })).not.toBeInTheDocument();
    expect(document.querySelector('a[href^="https://evil.example"]')).toBeNull();
  });

  it('the theme toggle sets data-theme and remembers the choice in localStorage only', async () => {
    renderApp('/jobs');
    await userEvent.click(await screen.findByRole('button', { name: /Switch to dark theme/ }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(window.localStorage.getItem('energiq.theme')).toBe('dark');
    await userEvent.click(await screen.findByRole('button', { name: /Switch to light theme/ }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('the active dataset is kept in sessionStorage, the token never reaches localStorage', async () => {
    renderApp('/');
    await screen.findByLabelText('Active dataset');
    await waitFor(() => expect(Object.keys(window.localStorage)).not.toContain('energiq.token'));
    const select = screen.getByLabelText('Active dataset') as HTMLSelectElement;
    await userEvent.selectOptions(select, String(fx.datasetsList[0]?.id));
    expect(window.sessionStorage.getItem('energiq.activeDataset')).toBe(String(fx.datasetsList[0]?.id));
    expect(JSON.stringify({ ...window.localStorage })).not.toContain('captured-session-token');
  });

  it('the sidebar offers every main page and only the Admin link for admins', async () => {
    const { unmount } = renderApp('/jobs', { role: 'analyst' });
    const nav = await screen.findByRole('navigation', { name: 'Main' });
    for (const name of ['Dashboard', 'Datasets', 'Forecast', 'Models', 'Anomalies', 'Explainability', 'Optimisation', 'Benchmark', 'Jobs']) {
      expect(within(nav).getByRole('link', { name })).toBeInTheDocument();
    }
    expect(within(nav).queryByRole('link', { name: 'Admin' })).not.toBeInTheDocument();
    unmount();
    renderApp('/jobs', { role: 'admin' });
    expect(within(await screen.findByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'Admin' })).toBeInTheDocument();
  });
});
