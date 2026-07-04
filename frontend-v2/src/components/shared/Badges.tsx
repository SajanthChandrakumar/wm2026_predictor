import { flag, cn } from '../../lib/util'
import { pointsTier, TIER_STYLES } from '../../lib/points'
import type { TeamForm } from '../../lib/types'

export function TeamLabel({ name, disp, className }: { name: string; disp?: string; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 font-semibold text-fg', className)}>
      <span aria-hidden>{flag(name)}</span>
      <span className="truncate">{disp?.replace(/^\p{RI}\p{RI}\s*/u, '') || name}</span>
    </span>
  )
}

const FORM_STYLE: Record<string, string> = {
  W: 'bg-emerald-dim text-emerald-a',
  D: 'bg-surface-2 text-fg-3',
  L: 'bg-red-a/10 text-red-a',
}

export function FormBadges({ form, className }: { form?: TeamForm; className?: string }) {
  if (!form?.form?.length) return null
  return (
    <span className={cn('inline-flex items-center gap-0.5', className)}>
      {form.form.slice(-5).map((r, i) => (
        <span
          key={i}
          className={cn('flex h-4 w-4 items-center justify-center rounded text-[9px] font-extrabold', FORM_STYLE[r])}
        >
          {r === 'W' ? 'S' : r === 'D' ? 'U' : 'N'}
        </span>
      ))}
      {form.on_fire && <span title="On fire" className="ml-0.5 text-[11px]">🔥</span>}
    </span>
  )
}

export function PointsBadge({ points }: { points: number | null | undefined }) {
  const tier = pointsTier(points)
  return (
    <span
      className={cn(
        'inline-flex min-w-7 items-center justify-center rounded-md border px-1.5 py-0.5',
        'display-num text-sm', TIER_STYLES[tier],
      )}
    >
      {points ?? '–'}
    </span>
  )
}

const RANK_STYLE: Record<number, string> = {
  1: 'bg-gold-dim text-gold-a border-gold-a/40',
  2: 'bg-surface-2 text-fg-2 border-line-2',
  3: 'bg-amber-a/10 text-amber-a border-amber-a/30',
}

export function RankBadge({ rank }: { rank: number }) {
  return (
    <span
      className={cn(
        'inline-flex h-7 w-7 items-center justify-center rounded-full border display-num text-sm',
        RANK_STYLE[rank] ?? 'border-line text-fg-3',
      )}
    >
      {rank}
    </span>
  )
}

export function TipBadge({ tip, highlight, className }: { tip?: string | null; highlight?: boolean; className?: string }) {
  if (!tip || tip === 'N/A') {
    return <span className={cn('rounded-lg border border-line px-2.5 py-1 text-sm text-fg-3', className)}>–</span>
  }
  return (
    <span
      className={cn(
        'rounded-lg border px-2.5 py-1 display-num text-base',
        highlight
          ? 'border-emerald-a/40 bg-emerald-dim text-emerald-a'
          : 'border-line-2 bg-surface-2 text-fg',
        className,
      )}
    >
      {tip}
    </span>
  )
}
