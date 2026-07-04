import { useMemo } from 'react'
import { motion } from 'framer-motion'
import { useMatches } from '../../hooks/queries'
import { PageTransition, PageHeader } from '../../components/shared/PageTransition'
import { RankBadge } from '../../components/shared/Badges'
import { FixtureRow } from '../dashboard/FixtureRow'

export function ValueBetsView() {
  const { data: matches, isLoading } = useMatches()

  const ranked = useMemo(
    () => (matches ?? []).filter((m) => m.max_xp > 0).sort((a, b) => b.max_xp - a.max_xp),
    [matches],
  )

  return (
    <PageTransition>
      <PageHeader title="Top Value Bets" subtitle="Spiele mit den höchsten erwarteten Punkten (xP)" />
      {isLoading && <p className="text-fg-2">Lade…</p>}

      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }} className="glass overflow-hidden !p-0">
        {ranked.map((m, i) => (
          <div key={m.id} className="flex items-center gap-3 border-b border-line pl-4 last:border-b-0">
            <RankBadge rank={i + 1} />
            <div className="min-w-0 flex-1">
              <FixtureRow
                match={m}
                trailing={
                  <span className="text-right">
                    <span className="display-num block text-lg text-emerald-a">{m.max_xp.toFixed(2)}</span>
                    <span className="block text-[10px] uppercase tracking-wider text-fg-3">xP · {m.top_tip}</span>
                  </span>
                }
              />
            </div>
          </div>
        ))}
      </motion.div>
    </PageTransition>
  )
}
