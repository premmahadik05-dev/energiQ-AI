import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ChartFrame, ChartSurface, type LegendItem } from './charts/ChartFrame';
import { ErrorBoundary } from './ErrorBoundary';
import { fx } from '../test/fixtures';
import { renderApp } from '../test/harness';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const legend2: LegendItem[] = [
  { label: 'Actual load (kW)', color: 'var(--s1)', kind: 'line' },
  { label: 'Forecast (kW)', color: 'var(--s2)', kind: 'dash' },
];

describe('ChartFrame (every chart has a legend for 2+ series and a table alternative)', () => {
  it('shows the legend for two series and switches to the table view with the same numbers', async () => {
    render(
      <ChartFrame title="Load" summary="Two series over four days." legend={legend2} table={<table><caption>values</caption><tbody><tr><td>1.36</td></tr></tbody></table>}>
        <ChartSurface>
          <svg data-testid="plot" />
        </ChartSurface>
      </ChartFrame>,
    );
    expect(screen.getByRole('list', { name: 'Chart legend' })).toHaveTextContent('Forecast (kW)');
    expect(screen.getByTestId('plot')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Two series over four days.' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'Table' }));
    expect(screen.getByText('1.36')).toBeInTheDocument();
    expect(screen.queryByTestId('plot')).not.toBeInTheDocument();
  });

  it('announces only the drawing as an image, so controls beside it stay reachable', () => {
    render(
      <ChartFrame title="Load" summary="One series." table={<table />}>
        <button type="button">Zoom in</button>
        <ChartSurface>
          <svg data-testid="plot" />
        </ChartSurface>
      </ChartFrame>,
    );
    const image = screen.getByRole('img', { name: 'One series.' });
    expect(image).toContainElement(screen.getByTestId('plot'));
    expect(image).not.toContainElement(screen.getByRole('button', { name: 'Zoom in' }));
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
    expect(screen.getByRole('link', { name: 'Go to the overview' })).toHaveAttribute('href', '/');
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

  it('the token never reaches localStorage', async () => {
    renderApp('/');
    expect(await screen.findByRole('heading', { name: 'Society overview' })).toBeInTheDocument();
    expect(Object.keys(window.localStorage)).not.toContain('energiq.token');
    expect(JSON.stringify({ ...window.localStorage })).not.toContain('captured-session-token');
  });

  it('the sidebar offers the society pages and the system pages, and only admins see Society admin and Admin', async () => {
    const { unmount } = renderApp('/jobs', { role: 'analyst' });
    const nav = await screen.findByRole('navigation', { name: 'Main' });
    for (const name of ['Society overview', 'Consumption', 'Forecasting', 'Buildings', 'Common facilities', 'Cost and peaks', 'Alerts', 'Recommendations', 'Reports', 'Data sources', 'Jobs']) {
      expect(within(nav).getByRole('link', { name })).toBeInTheDocument();
    }
    // the single-meter section is gone, heading and links
    expect(within(nav).queryByText('Single-meter tools')).not.toBeInTheDocument();
    for (const name of ['Dashboard', 'Datasets', 'Forecast', 'Models', 'Anomalies', 'Explainability', 'Optimisation', 'Benchmark']) {
      expect(within(nav).queryByRole('link', { name })).not.toBeInTheDocument();
    }
    expect(within(nav).queryByRole('link', { name: 'Admin' })).not.toBeInTheDocument();
    expect(within(nav).queryByRole('link', { name: 'Society admin' })).not.toBeInTheDocument();
    unmount();
    renderApp('/jobs', { role: 'admin' });
    const adminNav = await screen.findByRole('navigation', { name: 'Main' });
    expect(within(adminNav).getByRole('link', { name: 'Admin' })).toBeInTheDocument();
    expect(within(adminNav).getByRole('link', { name: 'Society admin' })).toBeInTheDocument();
  });
});
