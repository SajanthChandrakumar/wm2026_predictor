import type { Match } from '../../lib/types'
import { buildMatchHint } from '../../lib/matchHint'
import { cn } from '../../lib/util'

const confidenceStyle = {
  high: 'bg-emerald-dim text-emerald-a',
  medium: 'bg-blue-a/10 text-blue-a',
  low: 'bg-orange-a/10 text-orange-a',
} as const

export function MatchHintCard({ match }: { match: Match }) {
  const hint = buildMatchHint(match)
  const badgeStyle = hint.confidence === 'unavailable' ? '' : confidenceStyle[hint.confidence]

  return (
    <div>
      {hint.available && (
        <span className={cn('inline-flex rounded-full px-2.5 py-1 text-base font-bold', badgeStyle)}>
          Sicherheit: {hint.confidenceLabel}
        </span>
      )}
      <p className={cn('text-base font-semibold leading-snug text-fg', hint.available && 'mt-2')}>
        {hint.summary}
      </p>
      <p className="mt-1 text-base font-semibold text-fg-3">{hint.sourceLabel}</p>

      {hint.reasons.length > 0 && (
        <details className="group/hint mt-2 border-t border-line pt-1">
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between text-base font-bold text-blue-a focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-a/50">
            Warum?
            <span aria-hidden="true" className="text-lg transition-transform group-open/hint:rotate-90">›</span>
          </summary>
          <ul className="space-y-2 pb-1 text-base leading-relaxed text-fg-2">
            {hint.reasons.map((reason) => <li key={reason}>• {reason}</li>)}
          </ul>
        </details>
      )}
    </div>
  )
}
