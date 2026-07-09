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

  // Thin out X-axis labels once there are many matches, so they don't overlap into a smudge.
  const tickInterval = rows.length > 24 ? Math.ceil(rows.length / 12) : rows.length > 12 ? 1 : 0

  return (
    <GlassCard>
      <SectionTitle className="mb-4">Points Race</SectionTitle>
      <div className="h-96">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 4, right: 16, bottom: 12, left: -4 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: 'var(--text-3)', fontSize: 10 }}
              interval={tickInterval}
              angle={-40}
              textAnchor="end"
              height={56}
              tickMargin={8}
              tickLine={false}
              axisLine={{ stroke: 'var(--border)' }}
            />
            <YAxis tick={{ fill: 'var(--text-3)', fontSize: 11 }} tickLine={false} axisLine={false} width={44} />
            <Tooltip
              contentStyle={{
                background: 'var(--surface-2)', border: '1px solid var(--border-2)',
                borderRadius: 12, fontSize: 12, backdropFilter: 'blur(14px)',
              }}
              labelStyle={{ color: 'var(--text-2)', fontWeight: 700 }}
            />
            <Legend
              wrapperStyle={{ fontSize: 12, paddingTop: 16, display: 'flex', flexWrap: 'wrap', gap: '4px 16px', justifyContent: 'center' }}
              iconSize={10}
            />
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
