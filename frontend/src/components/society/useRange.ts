import { useState } from 'react';
import type { SocietySummary } from '../../api/societyTypes';
import { presetRange, type RangePreset } from '../../lib/societySeries';

/** Preset buttons' state plus the resulting start/end range (clamped to the society's own data period). */
export function useRange(society: SocietySummary, initial: RangePreset = '90d') {
  const [preset, setPreset] = useState<RangePreset>(initial);
  const range = presetRange(preset, society.start, society.end);
  return { preset, setPreset, range, key: `${society.id}:${range.start}:${range.end}` };
}
