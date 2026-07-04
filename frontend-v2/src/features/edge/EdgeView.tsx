import { useMemo } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { useMatches } from '../../hooks/queries'
import { flag, cn } from '../../lib/util'
import { shortDate } from '../../lib/format'
import { PageTransition, PageHeader, staggerContainer, staggerItem } from '../../components/shared/PageTransition'

/** Edge = Elo-share − Markt-share im Sieg/Niederlage-Pool (Prozentpunkte). */
export function EdgeView() {
  const { data: matches, isLoading } = useMatches()
  const navigate = useNavigate()

  const cards = useMemo(() => {
    const now = Date.now()
    return (matches ?? [])
      .filter((m) => {
        const ct = m.raw_match?.commence_time
        return m.edge_home != null && ct && new Date(String(ct)).getTime() > now
      })
      .sort((a, b) => Math.abs(b.edge_home!) - Math.abs(a.edge_home!))
  }, [matches])

  return (
    <PageTransition>
      <PageHeader title="Model Edge" subtitle="Wo das Elo-Modell den Buchmachern am stärksten widerspricht" />
      {isLoading && <p className="text-fg-2">Lade…</p>}
      {!isLoading && cards.length === 0 && <p className="text-fg-2">Keine kommenden Spiele mit Edge-Daten.</p>}

      <motion.div
        variants={staggerContainer} initial="initial" animate="animate"
        className="grid gap-4 md:grid-cols-2"
      >
        {cards.map((m) => {
          const edgePp = (m.edge_home ?? 0) * 100
          const abs = Math.abs(edgePp)
          const evFavHome = edgePp > 0
          const favTeam = evFavHome ? m.home_team : m.away_team
          const strength = abs >= 12 ? 'text-emerald-a' : abs >= 6 ? 'text-amber-a' : 'text-fg-3'
          const market = (m.market_home_share ?? 0.5) * 100
          const elo = (m.elo_home_share ?? 0.5) * 100

          return (
            <motion.button
              key={m.id}
              variants={staggerItem}
              onClick={() => navigate(`/match/${m.id}`)}
              className="glass glass-hover p-5 text-left"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-semibold text-fg">
                    {flag(m.home_team)} {m.home_team} <span className="text-fg-3">vs</span> {flag(m.away_team)} {m.away_team}
                  </div>
                  <div className="mt-0.5 text-xs text-fg-3">{shortDate(String(m.raw_match?.commence_time))}</div>
                </div>
                <div className={cn('display-num text-2xl', strength)}>
                  {edgePp > 0 ? '+' : ''}{edgePp.toFixed(1)}
                  <span className="ml-0.5 text-xs font-semibold">pp</span>
                </div>
              </div>

              <div className="mt-3 text-xs font-semibold text-fg-2">
                Modell favorisiert <b className="text-fg">{favTeam}</b> stärker als der Markt
              </div>

              <div className="mt-3 space-y-2">
                <Bar label="Markt" value={market} color="var(--text-3)" />
                <Bar label="Elo" value={elo} color="var(--emerald)" />
              </div>
            </motion.button>
          )
        })}
      </motion.div>
    </PageTransition>
  )
}

function Bar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-12 text-[10px] font-bold uppercase tracking-wider text-fg-3">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full" style={{ width: `${value}%`, background: color }} />
      </div>
      <span className="w-10 text-right text-xs tabular-nums text-fg-2">{value.toFixed(0)}%</span>
    </div>
  )
}
