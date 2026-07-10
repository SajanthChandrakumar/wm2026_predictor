import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMatches, usePredict, useSaveUserTip } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { computeImpliedProbs, pct, flag, cn } from '../../lib/util'
import type { BotKey, Match } from '../../lib/types'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { FormBadges } from '../../components/shared/Badges'
import { PageTransition } from '../../components/shared/PageTransition'
import { ChartSkeleton, CardGridSkeleton } from '../../components/shared/Skeleton'
import { Switch } from '../../components/ui/Switch'
import { ScoreHeatmap } from './ScoreHeatmap'

const BOT_META: Record<BotKey, { label: string; color: string }> = {
  broker: { label: 'Broker', color: 'var(--blue)' },
  professor: { label: 'Professor', color: 'var(--emerald)' },
  sniper: { label: 'X-Sniper', color: 'var(--purple)' },
  gambler: { label: 'Zocker', color: 'var(--text-2)' },
}

export function DetailView() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: matches } = useMatches()
  const { koPhase, setKoPhase } = useAppState()
  const predict = usePredict()
  const saveTip = useSaveUserTip()
  const [adoptStatus, setAdoptStatus] = useState('')

  const match: Match | undefined = useMemo(
    () => matches?.find((m) => m.id === id),
    [matches, id],
  )

  // Sync KO toggle with the match's own flag once, then recalc on every change.
  useEffect(() => {
    if (match?.raw_match) predict.mutate({ match: match.raw_match, isKo: koPhase })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [match?.id, koPhase])

  if (!matches) {
    return (
      <PageTransition>
        <div className="space-y-4">
          <ChartSkeleton />
          <CardGridSkeleton count={2} />
        </div>
      </PageTransition>
    )
  }
  if (!match) return <p className="text-red-a">Match nicht gefunden.</p>

  const calc = predict.data
  const probs = computeImpliedProbs(match.odds)
  const topTip = calc?.xp_tips?.[0]
  const runners = calc?.xp_tips?.slice(1, 4) ?? []
  const h2h = match.h2h
  const missing = Object.entries(match.lineup_diff ?? {}).filter(([, v]) => v.missing?.length)

  const adopt = () => {
    if (!topTip) return
    setAdoptStatus('Speichere…')
    saveTip.mutate(
      { matchId: match.id, tip: topTip.Tipp },
      {
        onSuccess: () => setAdoptStatus('✓ Übernommen'),
        onError: (e) => setAdoptStatus(`Fehler: ${(e as Error).message}`),
      },
    )
  }

  return (
    <PageTransition>
      <button onClick={() => navigate(-1)} className="mb-4 text-sm font-semibold text-fg-2 hover:text-fg">
        ← Zurück
      </button>

      {/* Header */}
      <header className="mb-6">
        <h1 className="font-display text-4xl font-extrabold uppercase tracking-wide text-fg">
          {flag(match.home_team)} {match.home_team} <span className="text-fg-3">vs</span>{' '}
          {flag(match.away_team)} {match.away_team}
        </h1>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Chip>{koPhase ? 'K.O. Phase — Punkte ×2' : 'Gruppenphase'}</Chip>
          {calc && <Chip>xG {calc.xg_home.toFixed(2)} : {calc.xg_away.toFixed(2)}</Chip>}
          {h2h && Object.keys(h2h).length > 0 && (
            <Chip>
              H2H {h2h[String(match.home_team_id ?? '')] ?? 0}–{h2h.draws ?? 0}–{h2h[String(match.away_team_id ?? '')] ?? 0}
            </Chip>
          )}
          <label className="ml-auto flex items-center gap-2 text-sm text-fg-2">
            K.O. Phase
            <Switch checked={koPhase} onCheckedChange={setKoPhase} />
          </label>
        </div>
      </header>

      {/* Lineup alert */}
      {missing.length > 0 && (
        <GlassCard className="mb-4 border-amber-a/40 bg-amber-a/5">
          <SectionTitle className="mb-2 text-amber-a">Aufstellungs-Alarm</SectionTitle>
          {missing.map(([team, v]) => (
            <p key={team} className="text-sm text-fg-2">
              <b className="text-fg">{team}:</b> fehlend — {v.missing.join(', ')}
            </p>
          ))}
        </GlassCard>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* xG + Form */}
        <GlassCard>
          <SectionTitle className="mb-4">Expected Goals & Form</SectionTitle>
          <div className="grid grid-cols-2 gap-4">
            {[
              { team: match.home_team, xg: calc?.xg_home, form: match.home_form },
              { team: match.away_team, xg: calc?.xg_away, form: match.away_form },
            ].map(({ team, xg, form }) => (
              <div key={team} className="text-center">
                <div className="text-sm font-semibold text-fg-2">{flag(team)} {team}</div>
                <div className="display-num mt-1 text-4xl text-emerald-a">{xg?.toFixed(2) ?? '…'}</div>
                <div className="mt-2 flex justify-center"><FormBadges form={form} /></div>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Bookmaker odds */}
        <GlassCard>
          <SectionTitle className="mb-4">Buchmacher-Quoten</SectionTitle>
          <div className="space-y-3">
            {[
              { label: `${match.home_team} Sieg`, price: match.odds?.home, p: probs.home, color: 'var(--blue)' },
              { label: 'Unentschieden', price: match.odds?.draw, p: probs.draw, color: 'var(--text-3)' },
              { label: `${match.away_team} Sieg`, price: match.odds?.away, p: probs.away, color: 'var(--red)' },
            ].map(({ label, price, p, color }) => (
              <div key={label}>
                <div className="flex items-baseline justify-between text-sm">
                  <span className="font-semibold text-fg">{label}</span>
                  <span className="tabular-nums text-fg-2">
                    {pct(p)} · <b className="text-fg">{price?.toFixed(2) ?? '–'}</b>
                  </span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2">
                  <div className="h-full rounded-full transition-all" style={{ width: `${p * 100}%`, background: color }} />
                </div>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Heatmap */}
        <GlassCard>
          <SectionTitle className="mb-4">Score-Wahrscheinlichkeiten</SectionTitle>
          {calc ? (
            <ScoreHeatmap calc={calc} homeDisp={match.home_disp} awayDisp={match.away_disp} />
          ) : (
            <p className="text-sm text-fg-3">{predict.isPending ? 'Rechne…' : 'Keine Daten'}</p>
          )}
        </GlassCard>

        {/* Tip ladder + bots */}
        <GlassCard>
          <SectionTitle className="mb-4">Tipp-Empfehlung</SectionTitle>
          {topTip ? (
            <>
              <div
                className="flex items-center justify-between rounded-xl border border-emerald-a/40 bg-emerald-dim px-4 py-3"
                style={{ boxShadow: '0 0 28px -8px color-mix(in srgb, var(--emerald) 50%, transparent), inset 0 1px 0 rgba(255,255,255,0.06)' }}
              >
                <div>
                  <div className="text-[10px] font-bold uppercase tracking-widest text-emerald-a">Top Tipp</div>
                  <div className="display-num text-3xl text-fg">{topTip.Tipp}</div>
                </div>
                <div className="text-right">
                  <div className="text-[10px] font-bold uppercase tracking-widest text-fg-3">xP</div>
                  <div className="display-num text-2xl text-emerald-a">{topTip.xP.toFixed(2)}</div>
                </div>
              </div>
              <div className="mt-3 space-y-1.5">
                {runners.map((t, i) => (
                  <div key={t.Tipp} className="flex items-center justify-between rounded-lg bg-surface px-3 py-1.5 text-sm">
                    <span className="text-fg-2">#{i + 2} <b className="ml-1 text-fg tabular-nums">{t.Tipp}</b></span>
                    <span className="tabular-nums text-fg-3">{t.xP.toFixed(2)} xP</span>
                  </div>
                ))}
              </div>
              <button
                onClick={adopt}
                disabled={saveTip.isPending}
                className="mt-4 w-full rounded-xl bg-gold-a/90 px-4 py-2.5 text-sm font-bold text-black transition hover:brightness-110 disabled:opacity-50"
              >
                Tipp übernehmen
              </button>
              {adoptStatus && <p className="mt-2 text-center text-xs text-fg-2">{adoptStatus}</p>}
            </>
          ) : (
            <p className="text-sm text-fg-3">{predict.isPending ? 'Rechne…' : 'Keine Empfehlung verfügbar'}</p>
          )}

          {match.bots && Object.keys(match.bots).length > 0 && (
            <div className="mt-5 border-t border-line pt-4">
              <SectionTitle className="mb-2">Bot Tips</SectionTitle>
              <div className="grid grid-cols-2 gap-2">
                {(Object.keys(BOT_META) as BotKey[]).map((key) => {
                  const tip = match.bots?.[key]?.tip
                  if (!tip) return null
                  return (
                    <div key={key} className="flex items-center justify-between rounded-lg bg-surface px-3 py-1.5 text-sm">
                      <span className="font-semibold" style={{ color: BOT_META[key].color }}>{BOT_META[key].label}</span>
                      <span className="display-num text-fg">{tip}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </GlassCard>
      </div>
    </PageTransition>
  )
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className={cn('rounded-full border border-line bg-surface px-3 py-1 text-xs font-semibold text-fg-2')}>
      {children}
    </span>
  )
}
