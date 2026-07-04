import { useMemo } from 'react'
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { HOUSE_BOTS, type CompletedMatch, type ScoreRow } from './usePerformanceData'

/** Cumulative points per predictor over the played matches (oldest → newest). */
export function PointsRaceChart({ completed, extraBots }: {
  completed: CompletedMatch[]
  extraBots: ScoreRow[]
}) {
  const { rows, series } = useMemo(() => {
    const chrono = [...completed].sort((a, b) => a.sortDate.localeCompare(b.sortDate))
    const series = [
      { key: 'Du', color: '#d4af37', dash: '6 3' },
      ...HOUSE_BOTS.map((b) => ({ key: b.label, color: b.color, dash: undefined as string | undefined })),
      ...extraBots.map((b) => ({ key: b.label, color: b.color, dash: undefined as string | undefined })),
    ]
    const running: Record<string, number> = Object.fromEntries(series.map((s) => [s.key, 0]))

    const rows = chrono.map(({ id, entry, points }) => {
      const label = `${entry.metadata.home_team.slice(0, 3).toUpperCase()}–${entry.metadata.away_team.slice(0, 3).toUpperCase()}`
      running['Du'] += points
      const bp = entry.post_match_result.bot_points ?? {}
      for (const b of HOUSE_BOTS) running[b.label] += bp[b.key] ?? 0
      for (const eb of extraBots) running[eb.label] += eb.pointsByMatch?.[id] ?? 0
      return { label, ...running }
    })
    return { rows, series }
  }, [completed, extraBots])

  if (rows.length < 2) return null

  return (
    <GlassCard>
      <SectionTitle className="mb-4">Points Race</SectionTitle>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 4, right: 12, bottom: 0, left: -8 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" tick={{ fill: 'var(--text-3)', fontSize: 9 }} angle={-45} textAnchor="end" height={48} tickLine={false} axisLine={{ stroke: 'var(--border)' }} />
            <YAxis tick={{ fill: 'var(--text-3)', fontSize: 11 }} tickLine={false} axisLine={false} width={40} />
            <Tooltip
              contentStyle={{
                background: 'var(--surface-2)', border: '1px solid var(--border-2)',
                borderRadius: 12, fontSize: 12, backdropFilter: 'blur(14px)',
              }}
              labelStyle={{ color: 'var(--text-2)', fontWeight: 700 }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {series.map((s) => (
              <Line
                key={s.key} type="monotone" dataKey={s.key}
                stroke={s.color} strokeWidth={s.key === 'Du' ? 3 : 2}
                strokeDasharray={s.dash} dot={false} activeDot={{ r: 4 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </GlassCard>
  )
}
