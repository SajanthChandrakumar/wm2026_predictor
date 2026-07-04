import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

interface AppState {
  koPhase: boolean
  setKoPhase: (v: boolean) => void
  light: boolean
  toggleTheme: () => void
  selectedTeams: string[]
  toggleTeam: (team: string) => void
}

const Ctx = createContext<AppState | null>(null)
const MAX_TEAMS = 4

export function AppStateProvider({
  children, light, toggleTheme,
}: { children: ReactNode; light: boolean; toggleTheme: () => void }) {
  const [koPhase, setKoPhase] = useState(false)
  const [selectedTeams, setSelectedTeams] = useState<string[]>([])

  // FIFO eviction when a 5th team is selected (legacy behavior).
  const toggleTeam = useCallback((team: string) => {
    setSelectedTeams((prev) =>
      prev.includes(team)
        ? prev.filter((t) => t !== team)
        : [...prev.slice(prev.length >= MAX_TEAMS ? 1 : 0), team],
    )
  }, [])

  const value = useMemo(
    () => ({ koPhase, setKoPhase, light, toggleTheme, selectedTeams, toggleTeam }),
    [koPhase, light, toggleTheme, selectedTeams, toggleTeam],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAppState(): AppState {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAppState must be used within AppStateProvider')
  return ctx
}
