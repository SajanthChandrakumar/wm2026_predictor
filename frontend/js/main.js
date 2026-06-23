// App entry point — boots, wires events, and routes between views.
// Pulled in via <script type="module"> from index.html.

import { state, charts } from './state.js';
import { api } from './api.js?v=2';
import { renderMatchGrid } from './views/dashboard.js';
import { renderValueBets } from './views/value-bets.js';
import { renderEdgeView } from './views/edge.js';
import { renderDetail } from './views/detail.js?v=2';
import { loadPerformanceView, saveUserTip, editUserTip } from './views/performance.js';
import { loadTeamFormView, toggleTeamSelect } from './views/team-form.js';
import { loadGroupsView } from './views/groups.js';

// Inline `onclick="..."` handlers in dynamically-injected HTML can't see
// ES-module scope. Expose the handful that need it on window.
window.saveUserTip      = saveUserTip;
window.editUserTip      = editUserTip;
window.toggleTeamSelect = toggleTeamSelect;
window.showView         = showView;

document.addEventListener('DOMContentLoaded', () => {
    fetchQuota();
    fetchMatches();
    initSidebar();
});

// ── View router ───────────────────────────────────────────────
const VIEW_MAP = {
    'dashboard':   ['matches-view',     'nav-dashboard'],
    'value-bets':  ['value-bets-view',  'nav-value-bets'],
    'edge':        ['edge-view',        'nav-edge'],
    'elo-history': ['elo-history-view', 'nav-elo-history'],
    'groups':      ['groups-view',      'nav-groups'],
    'performance': ['performance-view', 'nav-performance'],
    'detail':      ['detail-view',      null],
    'loading':     ['loading-spinner',  null],
};

function showView(view) {
    Object.values(VIEW_MAP).forEach(([id]) =>
        document.getElementById(id).style.display = 'none');
    document.querySelectorAll('nav li').forEach(li => li.classList.remove('active'));

    const [viewId, navId] = VIEW_MAP[view] || VIEW_MAP.dashboard;
    document.getElementById(viewId).style.display = '';
    if (navId) document.getElementById(navId).classList.add('active');
}

// ── Sidebar wiring ────────────────────────────────────────────
function initSidebar() {
    document.getElementById('nav-dashboard').addEventListener('click',
        () => showView('dashboard'));
    document.getElementById('nav-value-bets').addEventListener('click', () => {
        showView('value-bets');
        renderValueBets(state.currentMatches, openMatch);
    });
    document.getElementById('nav-edge').addEventListener('click', () => {
        showView('edge');
        renderEdgeView(state.currentMatches, openMatch);
    });
    document.getElementById('nav-elo-history').addEventListener('click', () => {
        showView('elo-history');
        loadTeamFormView();
    });
    document.getElementById('nav-groups').addEventListener('click', () => {
        showView('groups');
        loadGroupsView();
    });
    document.getElementById('nav-performance').addEventListener('click', () => {
        showView('performance');
        loadPerformanceView();
    });

    document.getElementById('refresh-btn').addEventListener('click', () => {
        showView('loading');
        fetchMatches(true);
    });
    document.getElementById('sync-elo-btn').addEventListener('click', syncElo);

    document.getElementById('ko-toggle').addEventListener('change', () => {
        if (state.selectedMatchId) updatePrediction();
    });

    initThemeToggle();

    document.getElementById('back-btn').addEventListener('click', () => {
        state.selectedMatchId = null;
        showView('dashboard');
    });
}

function initThemeToggle() {
    const toggle = document.getElementById('theme-toggle');
    if (!toggle) return;
    if (localStorage.getItem('theme') === 'light') {
        document.body.setAttribute('data-theme', 'light');
        toggle.checked = true;
    }
    toggle.addEventListener('change', e => {
        if (e.target.checked) {
            document.body.setAttribute('data-theme', 'light');
            localStorage.setItem('theme', 'light');
        } else {
            document.body.removeAttribute('data-theme');
            localStorage.setItem('theme', 'dark');
        }
        if (state.selectedMatchId) updatePrediction();
        if (charts.elo) loadTeamFormView();
    });
}

// ── Sidebar action handlers ───────────────────────────────────
async function fetchQuota() {
    try {
        const data = await api.quota();
        const odds = data.odds || {};
        const fb   = data.football || {};
        document.getElementById('quota-odds-value').textContent = odds.remaining ?? '--';
        document.getElementById('quota-odds-delta').textContent = `${odds.used ?? '?'} used`;
        document.getElementById('quota-fb-value').textContent   = fb.remaining ?? '--';
        document.getElementById('quota-fb-delta').textContent   = `${fb.used ?? '?'} used`;
    } catch { /* sidebar widget — silent */ }
}

async function fetchMatches(force = false) {
    showView('loading');
    try {
        state.currentMatches = await api.matches(force);
        renderMatchGrid(state.currentMatches, openMatch);
        showView('dashboard');
        fetchQuota();
    } catch (e) {
        const p = document.createElement('p');
        p.style.color = 'var(--danger)';
        p.textContent = `Error: ${e.message}`;
        const spinner = document.getElementById('loading-spinner');
        spinner.innerHTML = '';
        spinner.appendChild(p);
    }
}

async function syncElo() {
    const btn = document.getElementById('sync-elo-btn');
    btn.disabled = true;
    btn.textContent = 'Syncing…';
    try {
        const data = await api.syncElo();
        btn.textContent = data.updates ? `✓ ${data.updates} updated` : '✓ Up to date';
    } catch {
        btn.textContent = '✗ Sync failed';
    }
    setTimeout(() => { btn.textContent = 'Sync Elo Ratings'; btn.disabled = false; }, 3000);
}

// ── Detail view orchestration ─────────────────────────────────
function openMatch(id) {
    state.selectedMatchId = id;
    const match = state.currentMatches.find(m => m.id === id);
    updatePrediction();
}

async function updatePrediction() {
    if (!state.selectedMatchId) return;
    const matchData = state.currentMatches.find(m => m.id === state.selectedMatchId);
    if (!matchData) return;

    showView('loading');
    try {
        state.lastCalcData = await api.predict({
            match: matchData.raw_match,
            is_ko: document.getElementById('ko-toggle').checked,
        });
        renderDetail(matchData, state.lastCalcData);
        showView('detail');
    } catch (e) {
        const spinner = document.getElementById('loading-spinner');
        const errorDiv = document.createElement('div');
        errorDiv.style.textAlign = 'center';
        const errorP = document.createElement('p');
        errorP.style.color = 'var(--danger)';
        errorP.style.fontWeight = '600';
        errorP.textContent = e.message;
        const backBtn = document.createElement('button');
        backBtn.textContent = '← Back';
        backBtn.className = 'sidebar-btn';
        backBtn.style.width = 'auto';
        backBtn.style.marginTop = '16px';
        backBtn.onclick = () => showView('dashboard');
        errorDiv.appendChild(errorP);
        errorDiv.appendChild(backBtn);
        spinner.innerHTML = '';
        spinner.appendChild(errorDiv);
    }
}
