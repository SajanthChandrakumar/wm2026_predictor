// Date/time formatting — Zurich-local, German locale (matches legacy behavior).

const TZ = 'Europe/Zurich'

export function kickoffTime(iso?: string | null): string {
  if (!iso) return '–'
  return new Date(iso).toLocaleTimeString('de-CH', {
    hour: '2-digit', minute: '2-digit', timeZone: TZ,
  })
}

export function dayHeading(iso: string): string {
  return new Date(iso)
    .toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long', timeZone: TZ })
    .toUpperCase()
}

/** Grouping key: YYYY-MM-DD in Zurich time. */
export function dayKey(iso: string): string {
  return new Date(iso).toLocaleDateString('sv-SE', { timeZone: TZ })
}

export function shortDate(iso?: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('de-CH', {
    weekday: 'short', day: '2-digit', month: 'short', timeZone: TZ,
  })
}

export function numericDate(iso?: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('de-CH', { day: '2-digit', month: '2-digit', timeZone: TZ })
}
