/** Client-side pre-check only; the server limit (ENERGIQ_MAX_UPLOAD_MB) is authoritative. */
export const MAX_UPLOAD_MB = Number(import.meta.env.VITE_MAX_UPLOAD_MB ?? 50) || 50;
