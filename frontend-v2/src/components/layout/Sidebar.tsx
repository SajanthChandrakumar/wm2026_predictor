import { NavLink } from 'react-router-dom'
import { useState } from 'react'
import { useQuota, useRefreshData, useSyncElo } from '../../hooks/queries'
import { useAppState } from '../../state/AppState'
import { Switch } from '../ui/Switch'
import { cn } from '../../lib/util'

const NAV = [
  { to: '/', icon: '▦', label: 'Dashboard' },
  { to: '/value-bets', icon: '↑', label: 'Top Value Bets' },
  { to: '/edge', icon: '⇄', label: 'Model Edge' },
  { to: '/team-form', icon: '∿', label: 'Team Form' },
  { to: '/groups', icon: '▤', label: 'Groups' },
  { to: '/performance', icon: '◈', label: 'Performance' },
]

function QuotaMeter() {
  const { data } = useQuota()
  const rows = [
    { label: 'Odds API', q: data?.odds },
    { label: 'Football API', q: data?.football },
  ]
  return (
    <div className="glass space-y-3 p-3.5">
      {rows.map(({ label, q }) => {
        const remaining = Number(q?.remaining)
        const used = Number(q?.used)
        const total = Number.isFinite(remaining) && Number.isFinite(used) ? remaining + used : null
        const pct = total ? (remaining / total) * 100 : 0
        return (
          <div key={label}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-fg-3">{label}</span>
              <span className="text-right">
                <span className="display-num text-lg text-fg">{q?.remaining ?? '…'}</span>
                <span className="ml-1 text-[10px] text-fg-3">/ {q?.used ?? '…'} used</span>
              </span>
            </div>
            <div className="mt-1 h-1 overflow-hidden rounded-full bg-surface-2">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${pct}%`,
                  background: pct > 30 ? 'var(--emerald)' : pct > 10 ? 'var(--amber)' : 'var(--red)',
                }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function SidebarButtons() {
  const refresh = useRefreshData()
  const sync = useSyncElo()
  const [syncMsg, setSyncMsg] = useState<string | null>(null)

  const onSync = () => {
    sync.mutate(undefined, {
      onSuccess: (r) => {
        setSyncMsg(r.status === 'success' ? `✓ ${r.updates} updated` : '✓ Aktuell')
        setTimeout(() => setSyncMsg(null), 3000)
      },
      onError: () => {
        setSyncMsg('✗ Sync failed')
        setTimeout(() => setSyncMsg(null), 3000)
      },
    })
  }

  return (
    <div className="space-y-2">
      <button
        onClick={() => refresh.mutate()}
        disabled={refresh.isPending}
        className="w-full rounded-xl px-4 py-2.5 text-sm font-bold text-black transition hover:brightness-110 disabled:opacity-50"
        style={{
          background: 'linear-gradient(135deg, var(--emerald), #4dd0c4)',
          boxShadow: '0 4px 20px -6px color-mix(in srgb, var(--emerald) 60%, transparent)',
        }}
      >
        {refresh.isPending ? 'Lade…' : 'Refresh Data'}
      </button>
      <button
        onClick={onSync}
        disabled={sync.isPending}
        className="w-full rounded-xl border border-line-2 bg-surface px-4 py-2.5 text-sm font-semibold text-fg-2 transition hover:bg-surface-2 disabled:opacity-50"
      >
        {sync.isPending ? 'Synce…' : (syncMsg ?? 'Sync Elo Ratings')}
      </button>
    </div>
  )
}

export function Sidebar() {
  const { koPhase, setKoPhase, light, toggleTheme } = useAppState()

  return (
    <aside className="flex w-64 shrink-0 flex-col gap-5 border-r border-line p-5 max-lg:w-full max-lg:border-r-0 max-lg:border-b">
      {/* Brand */}
      <div className="flex items-center gap-2.5">
        <span
          className="rounded-lg px-2 py-1 font-display text-sm font-black text-black"
          style={{
            background: 'linear-gradient(135deg, var(--emerald), #4dd0c4)',
            boxShadow: '0 0 18px color-mix(in srgb, var(--emerald) 45%, transparent)',
          }}
        >
          WC
        </span>
        <span className="font-display text-xl font-extrabold text-fg">
          2026 <span className="font-semibold text-fg-3">Predictor</span>
        </span>
      </div>

      <QuotaMeter />

      <nav>
        <div className="mb-2 text-[10px] font-bold uppercase tracking-[0.2em] text-fg-3">Views</div>
        <ul className="space-y-1">
          {NAV.map(({ to, icon, label }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  cn(
                    'relative flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-semibold transition',
                    isActive
                      ? 'bg-emerald-dim text-fg shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--emerald)_35%,transparent),0_0_16px_-6px_var(--emerald)]'
                      : 'text-fg-2 hover:bg-surface hover:text-fg',
                  )
                }
              >
                <span className="w-4 text-center text-emerald-a/80">{icon}</span>
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div>
        <div className="mb-2 text-[10px] font-bold uppercase tracking-[0.2em] text-fg-3">Match Settings</div>
        <label className="flex cursor-pointer items-center justify-between gap-2 rounded-xl px-3 py-2 hover:bg-surface">
          <span>
            <span className="block text-sm font-bold text-fg">K.O. Phase</span>
            <span className="block text-[11px] text-fg-3">Points doubled</span>
          </span>
          <Switch checked={koPhase} onCheckedChange={setKoPhase} />
        </label>
      </div>

      <div>
        <div className="mb-2 text-[10px] font-bold uppercase tracking-[0.2em] text-fg-3">Appearance</div>
        <label className="flex cursor-pointer items-center justify-between gap-2 rounded-xl px-3 py-2 hover:bg-surface">
          <span>
            <span className="block text-sm font-bold text-fg">Light Mode</span>
            <span className="block text-[11px] text-fg-3">Premium Beige Theme</span>
          </span>
          <Switch checked={light} onCheckedChange={toggleTheme} />
        </label>
      </div>

      <div className="mt-auto max-lg:mt-2">
        <SidebarButtons />
      </div>
    </aside>
  )
}
