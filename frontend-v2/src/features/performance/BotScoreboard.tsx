import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { cn } from '../../lib/util'
import { HOUSE_BOTS, type PerformanceTotals, type ScoreRow } from './usePerformanceData'
import type { BotKey } from '../../lib/types'

export function BotScoreboard({ totals, botStats, extraBots }: {
  totals: PerformanceTotals
  botStats: Record<BotKey, { pts: number; tipped: number; tendency: number }>
  extraBots: ScoreRow[]
}) {
  const [showStrategies, setShowStrategies] = useState(false)

  const rows = useMemo<ScoreRow[]>(() => {
    const out: ScoreRow[] = [
      {
        key: 'you', label: 'Du', color: 'var(--gold)', isUser: true,
        pts: totals.totalPoints, tipped: totals.completed, tendency: totals.correctTendency,
      },
      ...HOUSE_BOTS.filter((b) => botStats[b.key].tipped > 0).map((b) => ({
        key: b.key, label: b.label, color: b.color, ...botStats[b.key],
      })),
      ...extraBots,
    ]
    return out.sort((a, b) => b.pts - a.pts)
  }, [totals, botStats, extraBots])

  return (
    <GlassCard className="!p-0">
      <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
        <SectionTitle>Bot Scoreboard</SectionTitle>
        <button
          onClick={() => setShowStrategies((v) => !v)}
          className="rounded-lg border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-fg-2 transition hover:bg-surface-2"
        >
          {showStrategies ? '✕ Schließen' : 'ⓘ Wie funktionieren die Bots?'}
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] font-bold uppercase tracking-wider text-fg-3">
              <th className="px-5 py-2 text-left">Bot</th>
              <th className="px-2 py-2 text-right">Pts</th>
              <th className="px-2 py-2 text-right max-sm:hidden">Getippt</th>
              <th className="px-2 py-2 text-right">Ø/Spiel</th>
              <th className="px-5 py-2 text-right">Tendenz</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.key} className={cn('border-t border-line', r.isUser && 'bg-gold-dim/50')}>
                <td className="px-5 py-2.5">
                  <span className="mr-2 text-fg-3">{i + 1}.</span>
                  <span className={cn('font-bold')} style={{ color: r.color }}>{r.label}</span>
                </td>
                <td className="display-num px-2 py-2.5 text-right text-base" style={{ color: r.color }}>{r.pts}</td>
                <td className="px-2 py-2.5 text-right tabular-nums text-fg-2 max-sm:hidden">{r.tipped}</td>
                <td className="px-2 py-2.5 text-right tabular-nums text-fg-2">
                  {r.tipped > 0 ? (r.pts / r.tipped).toFixed(2) : '—'}
                </td>
                <td className="px-5 py-2.5 text-right tabular-nums text-fg-3">
                  {r.tipped > 0 ? `${Math.round((r.tendency / r.tipped) * 100)}%` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <AnimatePresence>
        {showStrategies && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="overflow-hidden border-t border-line"
          >
            <div className="space-y-3 p-5">
              <Strategy icon="A" color="var(--gold)" title="Algo — Das Haus-Modell">
                <b>70 % Buchmacher-Quoten + 30 % Elo-Ratings</b>, dann xG → Tor-für-Tor-Wahrscheinlichkeitsmatrix
                → der Tipp mit den meisten erwarteten Punkten (xP) gewinnt. <i>Verwendet in „Top Tipp".</i>
              </Strategy>
              <Strategy icon="B" color="#5b9bd5" title="Broker — Pure Buchmacher-Quoten">
                <b>100 % Markt, 0 % Elo.</b> Vertraut blind den Buchmachern. <i>Die „Weisheit der Crowd"-Strategie.</i>
              </Strategy>
              <Strategy icon="P" color="#4caf82" title="Professor — Pure Elo-Ratings">
                <b>100 % Elo, 0 % Markt.</b> Ignoriert die Buchmacher komplett.
                <i> Schlägt den Markt, wenn die Quoten falsch liegen — verliert hart, wenn der Markt recht hat.</i>
              </Strategy>
              <Strategy icon="X" color="#9b6dd1" title="X-Sniper — Draw-Spezialist">
                Tippt <b>immer ein Unentschieden</b> — das mit dem höchsten xP.
                <i> Hochrisiko: trifft selten, aber oft volle 10 Punkte.</i>
              </Strategy>
              <Strategy icon="Z" color="#9a9a9a" title="Zocker — Gewichteter Zufall">
                Würfelt aus den <b>Top-10-Tipps</b> nach xP-Gewicht. <i>Match-ID als Seed — reproduzierbarer „Zufall".</i>
              </Strategy>
              <div className="rounded-xl border border-dashed border-line bg-surface p-3 text-xs leading-relaxed text-fg-3">
                <b className="text-fg-2">Punkte-System (SRF Tippspiel):</b> Exakter Score = <b>10 Pt</b> ·
                Korrekte Tordifferenz = <b>8 Pt</b> · Richtige Tendenz = <b>5 Pt</b> · Falsch = <b>0 Pt</b>.
                In der K.O.-Phase verdoppeln sich die Punkte (×2).
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </GlassCard>
  )
}

function Strategy({ icon, color, title, children }: {
  icon: string; color: string; title: string; children: React.ReactNode
}) {
  return (
    <div className="flex gap-3">
      <span
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-black text-black"
        style={{ background: color }}
      >
        {icon}
      </span>
      <div>
        <div className="text-sm font-extrabold" style={{ color }}>{title}</div>
        <div className="text-xs leading-relaxed text-fg-2">{children}</div>
      </div>
    </div>
  )
}
