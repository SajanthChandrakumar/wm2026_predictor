import { useEffect, useRef, useState } from 'react'
import { useSaveCustomBot } from '../../hooks/queries'
import { isOwner } from '../../lib/ownerAuth'
import type { BotSimulation, CustomBot, CustomBotParams } from '../../lib/types'
import { GlassCard, SectionTitle } from '../../components/shared/GlassCard'
import { Slider } from '../../components/ui/Slider'
import { cn } from '../../lib/util'
import type { usePerformanceData } from './usePerformanceData'

const CYAN = '#2dd4bf'
const DEFAULTS: CustomBotParams = { market_weight: 0.7, risk: 0, draw_bias: 0, underdog_bias: 0 }

const SLIDERS: { key: keyof CustomBotParams; label: string; min: number; max: number; step: number }[] = [
  { key: 'market_weight', label: 'Markt ↔ Elo', min: 0, max: 1, step: 0.05 },
  { key: 'risk', label: 'Risiko', min: -1, max: 1, step: 0.1 },
  { key: 'underdog_bias', label: 'Underdog-Bias', min: 0, max: 6, step: 0.5 },
  { key: 'draw_bias', label: 'Unentschieden-Bias', min: 0, max: 6, step: 0.5 },
]

function sliderValueLabel(key: keyof CustomBotParams, v: number): string {
  if (key === 'market_weight') return `Markt ${Math.round(v * 100)}% · Elo ${Math.round((1 - v) * 100)}%`
  if (key === 'risk') return v > 0 ? `Zocker +${v.toFixed(1)}` : v < 0 ? `Sicher ${v.toFixed(1)}` : 'Neutral'
  return v <= 0 ? 'aus' : `+${v.toFixed(1)}`
}

export function BuildABot({ customBot, simulate, userPoints, algoPoints }: {
  customBot: CustomBot | undefined
  simulate: ReturnType<typeof usePerformanceData>['simulate']
  userPoints: number
  algoPoints: number
}) {
  const [params, setParams] = useState<CustomBotParams>(DEFAULTS)
  const [name, setName] = useState('Mein Bot')
  const [sim, setSim] = useState<BotSimulation | null>(null)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'error'>('idle')
  const save = useSaveCustomBot()
  const timer = useRef<ReturnType<typeof setTimeout>>(null)
  const initialized = useRef(false)

  // Prefill once from the saved config.
  useEffect(() => {
    if (initialized.current || !customBot) return
    initialized.current = true
    if (customBot.exists) {
      setParams({ ...DEFAULTS, ...customBot.params })
      setName(customBot.name ?? 'Mein Bot')
    }
  }, [customBot])

  // Debounced live simulation (300ms) — also runs on mount.
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      simulate.mutate(params, { onSuccess: setSim })
    }, 300)
    return () => { if (timer.current) clearTimeout(timer.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params])

  const onSave = () => {
    setSaveState('saving')
    save.mutate(
      { name: name || 'Mein Bot', params },
      {
        onSuccess: () => setSaveState('idle'),
        onError: () => {
          setSaveState('error')
          setTimeout(() => setSaveState('idle'), 2200)
        },
      },
    )
  }

  return (
    <GlassCard>
      <SectionTitle className="mb-1">Build Your Bot</SectionTitle>
      <p className="mb-4 text-xs leading-relaxed text-fg-2">
        Stell deine eigene Tipp-Strategie ein und schau live, wie sie rückwirkend abgeschnitten hätte.{' '}
        <b style={{ color: CYAN }}>Speichern</b> → dein Bot tritt dauerhaft im Scoreboard & im Race an.
      </p>

      <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
        {SLIDERS.map(({ key, label, min, max, step }) => (
          <div key={key}>
            <div className="mb-1.5 flex items-baseline justify-between gap-2">
              <label className="text-xs font-bold text-fg">{label}</label>
              <span className="text-[11px] font-bold" style={{ color: CYAN }}>
                {sliderValueLabel(key, params[key])}
              </span>
            </div>
            <Slider
              value={params[key]} min={min} max={max} step={step} accent={CYAN}
              onChange={(v) => setParams((p) => ({ ...p, [key]: v }))}
            />
          </div>
        ))}
      </div>

      <div className="mt-5 min-h-16">
        {sim ? (
          <>
            <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
              <span className="text-[10px] font-bold uppercase tracking-widest text-fg-3">Hätte dein Bot</span>
              <span className="display-num text-4xl leading-none" style={{ color: CYAN }}>{sim.total_points}</span>
              <span className="text-sm text-fg-2">
                Punkte · {Math.round(sim.tendency_rate * 100)}% Tendenz · {sim.matches} Spiele
              </span>
            </div>
            <div className="mt-2 flex gap-4 text-sm">
              <Delta label="Du" diff={sim.total_points - userPoints} />
              <Delta label="Algo" diff={sim.total_points - algoPoints} />
            </div>
          </>
        ) : (
          <span className="text-sm text-fg-3">{simulate.isPending ? 'Rechne…' : ''}</span>
        )}
      </div>

      {isOwner() && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={40}
            placeholder="Bot-Name"
            className="min-w-40 flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-fg outline-none placeholder:text-fg-3 focus:border-emerald-a/50"
          />
          <button
            onClick={onSave}
            disabled={saveState === 'saving'}
            className={cn(
              'rounded-xl border px-5 py-2 text-sm font-bold transition disabled:opacity-50',
              saveState === 'error' ? 'border-red-a text-red-a' : 'hover:brightness-110',
            )}
            style={saveState !== 'error' ? { borderColor: CYAN, color: CYAN, background: 'rgba(45,212,191,0.1)' } : undefined}
          >
            {saveState === 'saving' ? '…' : saveState === 'error' ? '✗ Fehler' : 'Save Bot'}
          </button>
        </div>
      )}
    </GlassCard>
  )
}

function Delta({ label, diff }: { label: string; diff: number }) {
  const color = diff > 0 ? 'text-emerald-a' : diff < 0 ? 'text-red-a' : 'text-fg-2'
  return (
    <span>
      <span className="text-xs text-fg-3">vs {label} </span>
      <b className={cn('tabular-nums', color)}>{diff > 0 ? '+' : ''}{diff}</b>
    </span>
  )
}
