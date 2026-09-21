import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import type { Match, Probabilities, TeamForm } from '../../lib/types'
import { kickoffTime } from '../../lib/format'
import { computeImpliedProbs } from '../../lib/util'
import { ProbBar } from '../../components/shared/ProbBar'
import { TeamLabel, TipBadge } from '../../components/shared/Badges'
import { staggerItem } from '../../components/shared/PageTransition'

/** Subtle "on fire" indicator — full form chains live in Detail/Team Form. */
function FireDot({ form }: { form?: TeamForm }) {
  if (!form?.on_fire) return null
  return <span title="On fire" className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-a" />
}

type PredictionDetails = { source: string; probabilities: Probabilities | null }

function predictionDetails(match: Match): PredictionDetails {
  const hasBookmakerOdds = Boolean(match.odds && [match.odds.home, match.odds.draw, match.odds.away].every((price) => Number.isFinite(price) && price > 1))
  if (hasBookmakerOdds) return { source: 'Buchmacherquote', probabilities: computeImpliedProbs(match.odds) }

  const probabilities = match.probabilities
  const hasModel = match.source_mode === 'elo-only' && Boolean(probabilities)
  if (hasModel && probabilities && probabilities.home + probabilities.draw + probabilities.away > 0) {
    return { source: 'Elo-Modellquote · nicht wettbar', probabilities }
  }
  return { source: 'Nicht verfügbar', probabilities: null }
}

function displayTeamName(team: string, display?: string): string {
  return display?.replace(/^\p{RI}\p{RI}\s*/u, '') || team
}

function favoriteStatement(match: Match, details: PredictionDetails): string {
  const probabilities = details.probabilities
  if (!probabilities) return 'Keine Quote oder Modellwahrscheinlichkeit verfügbar.'

  const candidates = [
    { value: probabilities.home, label: displayTeamName(match.home_team, match.home_disp) },
    { value: probabilities.draw, label: 'Ein Unentschieden' },
    { value: probabilities.away, label: displayTeamName(match.away_team, match.away_disp) },
  ]
  const favorite = candidates.reduce((best, candidate) => candidate.value > best.value ? candidate : best)
  return `${favorite.label} ist laut ${details.source.replace(' · nicht wettbar', '')} am wahrscheinlichsten.`
}

/** Shared fixture row — used by Dashboard and Value Bets. */
export function FixtureRow({ match, trailing }: { match: Match; trailing?: React.ReactNode }) {
  const navigate = useNavigate()
  const ct = match.raw_match?.commence_time
  const isPlayed = Boolean(match.completed || match.actual_score)
  const details = predictionDetails(match)

  return (
    <motion.button
      type="button"
      variants={staggerItem}
      onClick={() => navigate(`/match/${match.id}`)}
      aria-label={`${displayTeamName(match.home_team, match.home_disp)} gegen ${displayTeamName(match.away_team, match.away_disp)}`}
      className="glass-hover group w-full min-h-[48px] border-b border-line p-4 text-left last:border-b-0 sm:grid sm:grid-cols-[52px_1fr_auto_16px] sm:items-center sm:gap-4 sm:px-4 sm:py-3.5"
    >
      <span className="mb-3 flex items-center justify-between text-sm tabular-nums text-fg-3 sm:mb-0 sm:block">
        <span className="text-[10px] font-bold uppercase tracking-wider sm:hidden">Anstoß</span>
        {kickoffTime(ct)}
      </span>

      <span className="min-w-0">
        <span className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
          <span className="flex min-w-0 flex-1 items-center gap-1.5 sm:justify-end sm:text-right">
            <TeamLabel name={match.home_team} disp={match.home_disp} logo={match.home_logo} />
            <FireDot form={match.home_form} />
          </span>
          <span className="hidden w-40 shrink-0 sm:block">
            {isPlayed ? (
              <span className="flex items-center justify-center">
                <span className="display-num rounded-lg border border-line-2 bg-surface-2 px-3 py-0.5 text-base text-fg">
                  {match.actual_score ?? '–'}
                </span>
              </span>
            ) : (
              <ProbBar
                odds={match.odds}
                probabilities={match.probabilities}
                sourceMode={match.source_mode}
                observedAt={match.observed_at}
                oddsObservedAt={match.odds_observed_at}
              />
            )}
          </span>
          <span className="flex min-w-0 flex-1 items-center gap-1.5">
            <TeamLabel name={match.away_team} disp={match.away_disp} logo={match.away_logo} />
            <FireDot form={match.away_form} />
          </span>
        </span>
        <span className="mt-3 block rounded-xl bg-surface-2 p-3 sm:hidden">
          <span className="flex items-center justify-between gap-3">
            <span className="text-xs font-bold uppercase tracking-wider text-fg-3">Unser Tipp</span>
            <TipBadge tip={match.top_tip} highlight />
          </span>
          {isPlayed && <span className="mt-2 block text-sm font-semibold text-fg">Endstand: {match.actual_score ?? '–'}</span>}
          <span className="mt-2 block text-base leading-snug text-fg">{favoriteStatement(match, details)}</span>
          <span className="mt-1 block text-xs font-semibold text-fg-3">{details.source}</span>
        </span>
      </span>

      <span className="hidden sm:block">
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
      <span className="hidden text-fg-3 sm:block">›</span>
    </motion.button>
  )
}
