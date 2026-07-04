import { computeImpliedProbs, pct } from '../../lib/util'
import type { Odds } from '../../lib/types'

/** 3-segment implied-probability bar (home / draw / away). */
export function ProbBar({ odds, showLabels = true }: { odds?: Odds | null; showLabels?: boolean }) {
  const p = computeImpliedProbs(odds)
  const empty = p.home + p.draw + p.away === 0
  return (
    <div className="w-full">
      <div className="flex h-1.5 w-full gap-0.5 overflow-hidden rounded-full">
        {empty ? (
          <div className="h-full w-full bg-surface-2" />
        ) : (
          <>
            <div className="h-full rounded-l-full bg-blue-a transition-all" style={{ width: `${p.home * 100}%` }} />
            <div className="h-full bg-fg-3/50 transition-all" style={{ width: `${p.draw * 100}%` }} />
            <div className="h-full rounded-r-full bg-red-a transition-all" style={{ width: `${p.away * 100}%` }} />
          </>
        )}
      </div>
      {showLabels && (
        <div className="mt-1 flex justify-between text-[11px] font-semibold tabular-nums">
          <span className="text-blue-a">{pct(p.home)}</span>
          <span className="text-fg-3">{pct(p.draw)} X</span>
          <span className="text-red-a">{pct(p.away)}</span>
        </div>
      )}
    </div>
  )
}
