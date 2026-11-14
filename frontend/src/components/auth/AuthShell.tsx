import type { ReactNode } from 'react';
import { Icon, Logo } from '../ui/Icon';
import { DemandForecastFigure } from './DemandForecastFigure';

export const SUBTITLE = 'Intelligent Energy Forecasting & Smart Society Management';

const BENEFITS = [
  { icon: 'forecast', title: 'AI-Powered Demand Forecasting', text: 'Hourly to weekly forecasts, always compared with simple baselines.' },
  { icon: 'chart', title: 'Intelligent Consumption Analytics', text: 'Society, building and common-facility views of the same meters.' },
  { icon: 'bulb', title: 'Predictive Energy Optimisation', text: 'Peak and cost insights, with the evidence behind each one.' },
] as const;

function BrandMark() {
  return (
    <div className="flex items-center gap-3">
      <Logo className="h-10 w-10 shrink-0" />
      <div className="min-w-0">
        <p className="text-[19px] font-semibold leading-tight tracking-tight text-ink">EnergiQ AI</p>
        <p className="text-[13px] leading-snug text-muted">{SUBTITLE}</p>
      </div>
    </div>
  );
}

function Benefits({ className = '' }: { className?: string }) {
  return (
    <ul className={`grid gap-4 ${className}`}>
      {BENEFITS.map((b) => (
        <li key={b.title} className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-accent-soft text-accent">
            <Icon name={b.icon} className="h-[18px] w-[18px]" />
          </span>
          <div>
            <p className="text-[14px] font-semibold leading-snug text-ink">{b.title}</p>
            <p className="mt-0.5 text-[13px] leading-snug text-muted">{b.text}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

/**
 * Sign-in and registration frame. Desktop: brand and a real forecast figure on the left (55 %), the form on the right.
 * Tablet: compact brand, the form card and the three benefits. Phone: compact brand and the form. The form comes first in the page
 * order, so keyboard and screen-reader users reach it before the marketing panel.
 */
export function AuthShell({ children, footer }: { children: ReactNode; footer: ReactNode }) {
  return (
    <div className="min-h-screen bg-page lg:grid lg:grid-cols-[minmax(0,55fr)_minmax(0,45fr)]">
      <main id="main" className="flex min-h-screen flex-col px-4 py-8 sm:px-6 lg:order-2 lg:border-l lg:border-line lg:bg-surface lg:px-12 lg:py-12">
        <div className="mx-auto flex w-full max-w-[26rem] flex-1 flex-col justify-center sm:max-w-[28rem] lg:max-w-[25rem]">
          <div className="mb-7 lg:hidden">
            <BrandMark />
          </div>
          <div className="rounded-lg border border-line bg-surface p-6 shadow-card sm:p-8 lg:border-0 lg:bg-transparent lg:p-0 lg:shadow-none">{children}</div>
          <p className="mt-6 text-center text-[14px] text-ink-2">{footer}</p>
          <Benefits className="mt-10 hidden border-t border-line pt-8 md:grid lg:hidden" />
        </div>
      </main>

      <aside aria-label="About EnergiQ AI" className="relative hidden overflow-hidden lg:order-1 lg:flex lg:flex-col lg:justify-between lg:gap-8 lg:px-12 lg:py-10 xl:px-16">
        <div className="auth-grid pointer-events-none absolute inset-0" aria-hidden="true" />
        <div className="relative">
          <BrandMark />
        </div>
        <div className="relative max-w-[34rem]">
          <h2 className="text-[38px] font-semibold leading-[1.08] tracking-[-0.03em] text-ink xl:text-[44px]">Smarter Energy Decisions Start Here.</h2>
          <p className="mt-4 max-w-[32rem] text-pretty text-[16px] leading-relaxed text-ink-2">Forecast the electricity demand of your residential community, spot unusual consumption early and see where peaks and costs come from.</p>
        </div>
        <div className="relative w-full max-w-[40rem] space-y-7">
          <DemandForecastFigure />
          <Benefits className="grid-cols-1 gap-5 xl:grid-cols-3 xl:gap-6" />
        </div>
      </aside>
    </div>
  );
}
