import { HashRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { AppStateProvider } from './state/AppState'
import { useTheme } from './hooks/useTheme'
import { DashboardView } from './features/dashboard/DashboardView'
import { DetailView } from './features/detail/DetailView'
import { ValueBetsView } from './features/value-bets/ValueBetsView'
import { EdgeView } from './features/edge/EdgeView'
import { TeamFormView } from './features/team-form/TeamFormView'
import { GroupsView } from './features/groups/GroupsView'
import { PerformanceView } from './features/performance/PerformanceView'

export default function App() {
  const { light, toggle } = useTheme()
  return (
    <AppStateProvider light={light} toggleTheme={toggle}>
      <HashRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<DashboardView />} />
            <Route path="/match/:id" element={<DetailView />} />
            <Route path="/value-bets" element={<ValueBetsView />} />
            <Route path="/edge" element={<EdgeView />} />
            <Route path="/team-form" element={<TeamFormView />} />
            <Route path="/groups" element={<GroupsView />} />
            <Route path="/performance" element={<PerformanceView />} />
          </Route>
        </Routes>
      </HashRouter>
    </AppStateProvider>
  )
}
