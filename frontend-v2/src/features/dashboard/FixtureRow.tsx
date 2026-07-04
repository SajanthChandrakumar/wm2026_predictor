import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import type { Match, TeamForm } from '../../lib/types'
import { kickoffTime } from '../../lib/format'
import { ProbBar } from '../../components/shared/ProbBar'
import { TeamLabel, TipBadge } from '../../components/shared/Badges'
import { staggerItem } from '../../components/shared/PageTransition'

/** Subtle "on fire" indicator — full form chains live in Detail/Team Form. */
function FireDot({ form }: { form?: TeamForm }) {
  if (!form?.on_fire) return null
  return <span title="On fire" className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-a" />
}

/** Shared fixture row — used by Dashboard and Value Bets. */
export function FixtureRow({ match, trailing }: { match: Match; trailing?: React.ReactNode }) {
  const navigate = useNavigate()
  const ct = match.raw_match?.commence_time
  const isPlayed = Boolean(match.completed || match.actual_score)

  return (
    <motion.button
      variants={staggerItem}
      onClick={() => navigate(`/match/${match.id}`)}
      className="glass-hover grid w-full grid-cols-[52px_1fr_auto_16px] items-center gap-4 border-b border-line px-4 py-3.5 text-left last:border-b-0 max-sm:grid-cols-[1fr_auto]"
    >
      <span className="text-sm tabular-nums text-fg-3 max-sm:hidden">{kickoffTime(ct)}</span>

      <span className="min-w-0">
        <span className="flex items-center justify-between gap-3">
          <span className="flex min-w-0 flex-1 items-center justify-end gap-1.5 text-right">
            <TeamLabel name={match.home_team} disp={match.home_disp} />
            <FireDot form={match.home_form} />
          </span>
          <span className="w-40 shrink-0 max-sm:w-24">
            {isPlayed ? (
              /* Played: compact score pill instead of odds bars */
              <span className="flex items-center justify-center">
                <span className="display-num rounded-lg border border-line-2 bg-surface-2 px-3 py-0.5 text-base text-fg">
                  {match.actual_score ?? '–'}
                </span>
              </span>
            ) : (
              <ProbBar odds={match.odds} />
            )}
          </span>
          <span className="flex min-w-0 flex-1 items-center gap-1.5">
            <TeamLabel name={match.away_team} disp={match.away_disp} />
            <FireDot form={match.away_form} />
          </span>
        </span>
      </span>

      <span>
        {trailing ?? (
          isPlayed ? (
            <span className="text-right">
              <span className="block text-[9px] font-bold uppercase tracking-wider text-fg-3">Algo</span>
              <TipBadge tip={match.top_tip} className="!px-2 !py-0.5 !text-sm" />
            </span>
          ) : (
            <TipBadge tip={match.top_tip} />
          )
        )}
      </span>
      <span className="text-fg-3 max-sm:hidden">›</span>
    </motion.button>
  )
}
