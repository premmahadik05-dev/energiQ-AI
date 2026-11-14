import { useMemo, useState, type FormEvent } from 'react';
import { ApiError } from '../../api/client';
import { tariffApi } from '../../api/endpoints';
import type { Tariff } from '../../api/types';
import { WriteOnly } from '../../auth/guards';
import { LinesChart } from '../charts/CategoryCharts';
import { Badge, Card } from '../ui/basic';
import { Notice, Spinner } from '../ui/feedback';
import { CheckboxField, Segmented, SelectField, TextField } from '../ui/forms';
import { ConfirmDialog } from '../ui/Modal';
import { Table, type Column } from '../ui/Table';
import { CURRENCIES, buildRates, emptyDraft, rateSummary, validateDraft, type TariffDraft, type TariffErrors, type TariffField } from '../../lib/tariff';
import { fmtNum } from '../../lib/format';
import { useSociety } from '../../state/SocietyContext';
import { useToast } from '../../state/ToastContext';

const OTHER = '__other__';

/**
 * Create, select and delete the tariffs that price every cost figure. The built-in "demo" tariff is a placeholder; a
 * real estimate needs the rates from the person's own electricity bill, which only they know.
 */
export function TariffManager() {
  const { tariffs, tariffId, setTariffId, refreshTariffs } = useSociety();
  const toast = useToast();
  const [draft, setDraft] = useState<TariffDraft>(() => emptyDraft());
  const [currencyChoice, setCurrencyChoice] = useState<string>('INR');
  const [tried, setTried] = useState(false);
  const [serverErrors, setServerErrors] = useState<TariffErrors>({});
  const [busy, setBusy] = useState(false);
  const [toDelete, setToDelete] = useState<Tariff | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const errors = useMemo<TariffErrors>(() => ({ ...validateDraft(draft), ...serverErrors }), [draft, serverErrors]);
  const shown = (f: TariffField): string | undefined => (tried || serverErrors[f] ? errors[f] : undefined);
  const rates = useMemo(() => buildRates(draft), [draft]);

  const set = <K extends TariffField>(k: K, v: TariffDraft[K]) => {
    setDraft((d) => ({ ...d, [k]: v }));
    setServerErrors((s) => (s[k] ? { ...s, [k]: undefined } : s));
  };
  const pickCurrency = (choice: string) => {
    setCurrencyChoice(choice);
    set('currency', choice === OTHER ? '' : choice);
  };

  const submit = async (ev: FormEvent) => {
    ev.preventDefault();
    setTried(true);
    const built = buildRates(draft);
    if (!built) return;
    setBusy(true);
    try {
      const created = await tariffApi.create({ name: draft.name.trim(), currency: draft.currency.trim(), ...built });
      toast.push(`Tariff "${created.name}" saved and selected.`, 'success');
      setTariffId(created.id);
      refreshTariffs();
      setDraft(emptyDraft(draft.currency));
      setTried(false);
      setServerErrors({});
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setServerErrors({ name: 'You already have a tariff with this name' });
      else if (err instanceof ApiError && Object.keys(err.fieldErrors).length > 0) {
        const mapped: TariffErrors = {};
        for (const [k, v] of Object.entries(err.fieldErrors)) if (k in draft) mapped[k as TariffField] = v;
        setServerErrors(mapped);
        toast.push(err.message, 'error');
      } else toast.push(err instanceof Error ? err.message : 'The tariff could not be saved.', 'error');
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = async () => {
    if (!toDelete) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await tariffApi.remove(toDelete.id);
      if (String(tariffId) === String(toDelete.id)) setTariffId('demo');
      refreshTariffs();
      toast.push(`Tariff "${toDelete.name}" deleted.`, 'success');
      setToDelete(null);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'The tariff could not be deleted.');
    } finally {
      setDeleting(false);
    }
  };

  const columns: Column<Tariff>[] = [
    {
      key: 'n',
      header: 'Tariff',
      render: (t) => (
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{t.name}</span>
          {t.is_demo && <Badge tone="warn">Placeholder</Badge>}
          {String(t.id) === String(tariffId) && <Badge tone="good">In use</Badge>}
        </span>
      ),
    },
    { key: 'c', header: 'Currency', render: (t) => t.currency },
    { key: 'wd', header: 'Weekday rate per kWh', align: 'right', render: (t) => rateSummary(t.weekday_rates) },
    { key: 'we', header: 'Weekend rate per kWh', align: 'right', render: (t) => rateSummary(t.weekend_rates) },
    { key: 'f', header: 'Fixed per day', align: 'right', render: (t) => fmtNum(t.daily_fixed_charge, 2) },
    {
      key: 'a',
      header: 'Actions',
      render: (t) => (
        <span className="flex items-center gap-2">
          {String(t.id) !== String(tariffId) && (
            <button type="button" className="btn-ghost text-xs" onClick={() => setTariffId(t.id)} aria-label={`Use tariff ${t.name}`}>
              Use
            </button>
          )}
          {!t.is_demo && (
            <WriteOnly>
              <button type="button" className="btn-ghost text-xs text-bad" onClick={() => { setDeleteError(null); setToDelete(t); }} aria-label={`Delete tariff ${t.name}`}>
                Delete
              </button>
            </WriteOnly>
          )}
        </span>
      ),
    },
  ];

  const currency = draft.currency.trim() || '–';
  const chart = rates
    ? Array.from({ length: 24 }, (_, h) => ({ hour: String(h).padStart(2, '0'), weekday: rates.weekday_rates[h] as number, weekend: rates.weekend_rates[h] as number }))
    : null;

  return (
    <Card title="Tariffs" description="The price per kWh by hour of day that turns energy into a cost estimate. Pick the one to use, or add your own from an electricity bill.">
      <Table columns={columns} rows={tariffs} rowKey={(t) => String(t.id)} caption="Available tariffs with their rates and actions" dense />
      <WriteOnly>
        <form className="mt-6 space-y-4 border-t border-line pt-5" onSubmit={(e) => void submit(e)} noValidate aria-label="Add a tariff">
          <h3 className="text-base font-semibold">Add a tariff</h3>
          <Notice>
            EnergiQ does not know any real utility prices. Enter the rates printed on your own electricity bill; the figures on the Cost tab are then an estimate based on those rates, not a bill.
          </Notice>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <TextField label="Name" value={draft.name} onChange={(e) => set('name', e.target.value)} error={shown('name')} maxLength={80} placeholder="For example: Home meter, domestic slab" autoComplete="off" />
            <SelectField label="Currency" value={currencyChoice} onChange={(e) => pickCurrency(e.target.value)} error={currencyChoice === OTHER ? undefined : shown('currency')}>
              {CURRENCIES.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.label}
                </option>
              ))}
              <option value={OTHER}>Other…</option>
            </SelectField>
            {currencyChoice === OTHER ? (
              <TextField label="Currency code or symbol" value={draft.currency} onChange={(e) => set('currency', e.target.value)} error={shown('currency')} maxLength={8} placeholder="For example: AED" autoComplete="off" />
            ) : (
              <TextField label={`Fixed charge per day (${currency})`} inputMode="decimal" value={draft.fixedCharge} onChange={(e) => set('fixedCharge', e.target.value)} error={shown('fixedCharge')} hint="Use 0 if the bill has none" />
            )}
          </div>
          {currencyChoice === OTHER && (
            <div className="max-w-xs">
              <TextField label={`Fixed charge per day (${currency})`} inputMode="decimal" value={draft.fixedCharge} onChange={(e) => set('fixedCharge', e.target.value)} error={shown('fixedCharge')} hint="Use 0 if the bill has none" />
            </div>
          )}
          <div>
            <p className="label">Rate structure</p>
            <Segmented
              label="Rate structure"
              value={draft.mode}
              onChange={(v) => set('mode', v)}
              options={[
                { value: 'flat', label: 'One rate all day' },
                { value: 'window', label: 'Peak and off-peak' },
              ]}
            />
          </div>
          {draft.mode === 'flat' ? (
            <div className="max-w-xs">
              <TextField label={`Rate (${currency} per kWh)`} inputMode="decimal" value={draft.flatRate} onChange={(e) => set('flatRate', e.target.value)} error={shown('flatRate')} placeholder="For example: 7.5" />
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                <TextField label={`Off-peak rate (${currency} per kWh)`} inputMode="decimal" value={draft.offPeakRate} onChange={(e) => set('offPeakRate', e.target.value)} error={shown('offPeakRate')} />
                <TextField label={`Peak rate (${currency} per kWh)`} inputMode="decimal" value={draft.peakRate} onChange={(e) => set('peakRate', e.target.value)} error={shown('peakRate')} />
                <TextField label="Peak starts at hour" inputMode="numeric" value={draft.peakStart} onChange={(e) => set('peakStart', e.target.value)} error={shown('peakStart')} hint="0 to 23, e.g. 18 for 6 pm" />
                <TextField label="Peak ends before hour" inputMode="numeric" value={draft.peakEnd} onChange={(e) => set('peakEnd', e.target.value)} error={shown('peakEnd')} hint="0 to 23; may be earlier than the start to cross midnight" />
              </div>
              <CheckboxField label="The peak rate also applies on weekends" checked={draft.peakOnWeekend} onChange={(e) => set('peakOnWeekend', e.target.checked)} hint="Leave unticked if weekends are charged the off-peak rate all day" />
            </div>
          )}
          {chart ? (
            <div>
              <p className="mb-2 text-sm font-semibold">Rate by hour of day (preview of what will be saved)</p>
              <LinesChart
                data={chart}
                xKey="hour"
                series={[{ key: 'weekday', name: 'Weekday', color: 'var(--s1)' }, { key: 'weekend', name: 'Weekend', color: 'var(--s3)', dashed: true }]}
                unit={`${currency}/kWh`}
                digits={2}
                step
                zero
                xLabel="Hour of day"
                height={220}
              />
            </div>
          ) : (
            <p className="text-sm text-ink-2">The rate preview appears once every rate field holds a valid number.</p>
          )}
          <div className="flex items-center gap-3">
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy && <Spinner />}
              Save tariff
            </button>
            {tried && Object.values(errors).some(Boolean) && <span role="status" className="text-sm text-bad">Fix the highlighted fields to save.</span>}
          </div>
        </form>
      </WriteOnly>
      <ConfirmDialog open={toDelete !== null} title="Delete this tariff?" confirmLabel="Delete tariff" busy={deleting} error={deleteError ?? undefined} onCancel={() => setToDelete(null)} onConfirm={() => void confirmDelete()}>
        {toDelete?.name} is removed from your account. If it is the tariff in use, cost figures go back to the placeholder tariff.
      </ConfirmDialog>
    </Card>
  );
}
