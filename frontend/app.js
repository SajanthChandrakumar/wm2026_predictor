let currentMatches = [];
let selectedMatchId = null;
let lastCalcData = null;
let eloChartInstance = null;
let aggressivenessDebounce = null;

// ── Boot ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    fetchQuota();
    fetchMatches();
    initSidebar();
});

function initSidebar() {
    // Nav
    document.getElementById('nav-dashboard').addEventListener('click', () => showView('dashboard'));
    document.getElementById('nav-value-bets').addEventListener('click', () => {
        showView('value-bets');
        renderValueBets(currentMatches);
    });
    document.getElementById('nav-elo-history').addEventListener('click', () => {
        showView('elo-history');
        loadEloHistoryView();
    });
    document.getElementById('nav-performance').addEventListener('click', () => {
        showView('performance');
        loadPerformanceView();
    });

    // Buttons
    document.getElementById('refresh-btn').addEventListener('click', () => {
        showView('loading');
        fetchMatches(true);
    });
    document.getElementById('sync-elo-btn').addEventListener('click', syncElo);

    // Match toggles — re-predict on change
    ['ko-toggle', 'home-resting-toggle', 'away-resting-toggle'].forEach(id => {
        document.getElementById(id).addEventListener('change', () => {
            if (selectedMatchId) updatePrediction();
        });
    });

    // Back
    document.getElementById('back-btn').addEventListener('click', () => {
        selectedMatchId = null;
        showView('dashboard');
    });

    // Aggressiveness slider
    const slider = document.getElementById('aggressiveness-slider');
    slider.addEventListener('input', () => {
        updateStrategyUI(parseFloat(slider.value));
        if (!selectedMatchId) return;
        clearTimeout(aggressivenessDebounce);
        aggressivenessDebounce = setTimeout(() => updatePrediction(), 400);
    });
    updateStrategyUI(0);
}

// ── Views ─────────────────────────────────────────────────────
function showView(view) {
    ['matches-view', 'value-bets-view', 'elo-history-view', 'performance-view', 'detail-view', 'loading-spinner']
        .forEach(id => document.getElementById(id).style.display = 'none');

    document.querySelectorAll('nav li').forEach(li => li.classList.remove('active'));

    const map = {
        'dashboard':   ['matches-view',      'nav-dashboard'],
        'value-bets':  ['value-bets-view',   'nav-value-bets'],
        'elo-history': ['elo-history-view',  'nav-elo-history'],
        'performance': ['performance-view',  'nav-performance'],
        'detail':      ['detail-view',        null],
        'loading':     ['loading-spinner',    null],
    };
    const [viewId, navId] = map[view] || ['matches-view', 'nav-dashboard'];
    document.getElementById(viewId).style.display = '';
    if (navId) document.getElementById(navId).classList.add('active');
}

// ── Strategy UI ───────────────────────────────────────────────
function updateStrategyUI(val) {
    document.getElementById('aggressiveness-label').textContent = val.toFixed(1);
    const badge  = document.getElementById('strategy-badge');
    const hint   = document.getElementById('strategy-hint');

    if (val === 0) {
        badge.className = 'strategy-mode-badge';
        badge.textContent = 'Safe';
        hint.textContent = 'Tipping the most likely score. Best when leading or in a small pool.';
    } else if (val <= 0.3) {
        badge.className = 'strategy-mode-badge';
        badge.textContent = 'Soft';
        hint.textContent = 'Same tendency as the field, different exact score. Low cost, good differentiation.';
    } else if (val <= 0.7) {
        badge.className = 'strategy-mode-badge aggressive';
        badge.textContent = 'Contrarian';
        hint.textContent = 'Accepting lower average points to build a ceiling over the field. Good when chasing.';
    } else {
        badge.className = 'strategy-mode-badge max-aggro';
        badge.textContent = 'High Risk';
        hint.textContent = 'Maximum variance — betting the field gets the result completely wrong. KO phase / big deficit only.';
    }
}

// ── API Calls ─────────────────────────────────────────────────
async function fetchQuota() {
    try {
        const data = await (await fetch('/api/quota')).json();
        document.getElementById('quota-value').textContent = data.remaining ?? '--';
        document.getElementById('quota-delta').textContent = `${data.used ?? '?'} used`;
    } catch {}
}

async function fetchMatches(force = false) {
    showView('loading');
    try {
        const url = force ? '/api/matches?force=true' : '/api/matches';
        currentMatches = await (await fetch(url)).json();
        renderMatchGrid(currentMatches);
        showView('dashboard');
        fetchQuota();
    } catch (e) {
        document.getElementById('loading-spinner').innerHTML =
            `<p style="color:var(--danger)">Error: ${e.message}</p>`;
    }
}

async function syncElo() {
    const btn = document.getElementById('sync-elo-btn');
    btn.disabled = true;
    btn.textContent = 'Syncing…';
    try {
        const data = await (await fetch('/api/sync_elo', { method: 'POST' })).json();
        btn.textContent = data.updates ? `✓ ${data.updates} updated` : '✓ Up to date';
    } catch {
        btn.textContent = '✗ Sync failed';
    }
    setTimeout(() => { btn.textContent = 'Sync Elo Ratings'; btn.disabled = false; }, 3000);
}

async function updatePrediction() {
    if (!selectedMatchId) return;
    const matchData = currentMatches.find(m => m.id === selectedMatchId);
    if (!matchData) return;

    const aggressiveness = parseFloat(document.getElementById('aggressiveness-slider').value);
    showView('loading');

    try {
        const res = await fetch('/api/predict', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                match: matchData.raw_match,
                is_ko: document.getElementById('ko-toggle').checked,
                home_resting: document.getElementById('home-resting-toggle').checked,
                away_resting: document.getElementById('away-resting-toggle').checked,
                aggressiveness,
            })
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'API error');
        }
        lastCalcData = await res.json();
        renderDetail(matchData, lastCalcData);
        showView('detail');
    } catch (e) {
        document.getElementById('loading-spinner').innerHTML =
            `<div style="text-align:center"><p style="color:var(--danger);font-weight:600">${e.message}</p>
             <button onclick="showView('dashboard')" class="sidebar-btn" style="width:auto;margin-top:16px;">← Back</button></div>`;
    }
}

// ── Render: Match Grid (fixture-list grouped by day) ──────────
function renderMatchGrid(matches) {
    const grid = document.getElementById('matches-grid');
    grid.innerHTML = '';

    const sorted = [...matches].sort((a, b) =>
        new Date(a.raw_match.commence_time) - new Date(b.raw_match.commence_time));

    const groups = {};
    sorted.forEach(match => {
        const d = new Date(match.raw_match.commence_time);
        const key = d.toLocaleDateString('de-CH', {
            weekday: 'long', day: 'numeric', month: 'long',
            timeZone: 'Europe/Zurich'
        });
        if (!groups[key]) groups[key] = [];
        groups[key].push(match);
    });

    Object.entries(groups).forEach(([day, dayMatches]) => {
        const group = document.createElement('div');
        group.className = 'day-group';

        const header = document.createElement('div');
        header.className = 'day-header';
        header.textContent = day;
        group.appendChild(header);

        const list = document.createElement('div');
        list.className = 'fixture-group-list';
        dayMatches.forEach(match => {
            const row = buildFixtureRow(match);
            row.addEventListener('click', () => openMatch(match.id));
            list.appendChild(row);
        });
        group.appendChild(list);
        grid.appendChild(group);
    });
}

function renderValueBets(matches) {
    const grid = document.getElementById('value-bets-grid');
    grid.innerHTML = '';
    const sorted = [...matches]
        .filter(m => m.max_xp > 0)
        .sort((a, b) => b.max_xp - a.max_xp);

    const list = document.createElement('div');
    list.className = 'fixture-group-list';
    sorted.forEach(match => {
        const row = buildFixtureRow(match, true);
        row.addEventListener('click', () => openMatch(match.id));
        list.appendChild(row);
    });
    grid.appendChild(list);
}

function buildFixtureRow(match, showXp = false) {
    const row = document.createElement('div');
    row.className = 'fixture-row';

    const d = new Date(match.raw_match.commence_time);
    const now = new Date();
    const isPast = d < now;

    const timeStr = d.toLocaleTimeString('de-CH', {
        hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Zurich'
    });

    const probs = computeImpliedProbs(match.odds);
    const hPct = probs.home * 100, dPct = probs.draw * 100, aPct = probs.away * 100;

    const tipHtml = match.top_tip && match.top_tip !== 'N/A'
        ? `<div class="fixture-tip">${match.top_tip}</div>`
        : `<div class="fixture-tip na">–</div>`;

    const xpBadge = showXp && match.max_xp > 0
        ? `<div class="fixture-tip" style="color:var(--green);background:var(--green-dim);border-color:rgba(30,171,90,0.3)">${match.max_xp.toFixed(1)} xP</div>`
        : tipHtml;

    row.innerHTML = `
        <div class="fixture-time${isPast ? ' past' : ''}">${timeStr}</div>
        <div class="fixture-body">
            <div class="fixture-teams">
                <span class="fixture-home">${match.home_disp}</span>
                <div class="fix-bar">
                    <div class="bar-h" style="width:${hPct}%"></div>
                    <div class="bar-d" style="width:${dPct}%"></div>
                    <div class="bar-a" style="width:${aPct}%"></div>
                </div>
                <span class="fixture-away">${match.away_disp}</span>
            </div>
            <div class="fixture-probs">
                <span class="fp-h">${pct(probs.home)}</span>
                <span class="fp-d">${pct(probs.draw)} X</span>
                <span class="fp-a">${pct(probs.away)}</span>
            </div>
        </div>
        ${xpBadge}
        <div class="fixture-chevron">›</div>
    `;
    return row;
}

function openMatch(id) {
    selectedMatchId = id;
    const match = currentMatches.find(m => m.id === id);
    document.getElementById('home-resting-label').textContent = (match?.home_disp ?? 'Home') + ' rotates';
    document.getElementById('away-resting-label').textContent = (match?.away_disp ?? 'Away') + ' rotates';
    document.getElementById('home-resting-toggle').checked = false;
    document.getElementById('away-resting-toggle').checked = false;
    updatePrediction();
}

// ── Render: Detail View ───────────────────────────────────────
function renderDetail(matchInfo, calc) {
    const isKo = document.getElementById('ko-toggle').checked;

    // Title & meta
    document.getElementById('match-title').textContent =
        `${matchInfo.home_disp} vs ${matchInfo.away_disp}`;

    const metaChips = [
        isKo ? '<span class="meta-chip ko">🏆 K.O. Phase</span>' : '<span class="meta-chip">Group Stage</span>',
        `<span class="meta-chip">xG ${calc.xg_home.toFixed(2)} – ${calc.xg_away.toFixed(2)}</span>`,
    ];
    document.getElementById('match-meta').innerHTML = metaChips.join('');

    // xG row
    document.getElementById('xg-row').innerHTML = `
        <div class="xg-team home">
            <span class="xg-team-name">${matchInfo.home_disp}</span>
            <span class="xg-value">${calc.xg_home.toFixed(2)}</span>
            <span class="xg-label">Expected Goals</span>
        </div>
        <div class="xg-divider">
            <span>vs</span>
            <small>xG</small>
        </div>
        <div class="xg-team away">
            <span class="xg-team-name">${matchInfo.away_disp}</span>
            <span class="xg-value">${calc.xg_away.toFixed(2)}</span>
            <span class="xg-label">Expected Goals</span>
        </div>
    `;

    // Heatmap
    renderHeatmap(matchInfo, calc);

    // Odds
    const probs = computeImpliedProbs(matchInfo.odds);
    document.getElementById('odds-card').innerHTML = `
        <div class="card-title">Bookmaker Odds</div>
        <div class="odds-row">
            <span class="odds-team">${matchInfo.home_disp}</span>
            <div class="odds-right">
                <span class="odds-pct">${pct(probs.home)}</span>
                <span class="odds-price">${matchInfo.odds.home.toFixed(2)}</span>
            </div>
        </div>
        <div class="odds-row">
            <span class="odds-team" style="color:var(--text-secondary)">Draw</span>
            <div class="odds-right">
                <span class="odds-pct">${pct(probs.draw)}</span>
                <span class="odds-price">${matchInfo.odds.draw.toFixed(2)}</span>
            </div>
        </div>
        <div class="odds-row">
            <span class="odds-team">${matchInfo.away_disp}</span>
            <div class="odds-right">
                <span class="odds-pct">${pct(probs.away)}</span>
                <span class="odds-price">${matchInfo.odds.away.toFixed(2)}</span>
            </div>
        </div>
    `;

    // Safe tips
    renderSafeTips(calc.xp_tips);

    // Pool tips
    renderPoolTips(calc.pool_tips);

    // Keep active tab
    const activeTab = document.querySelector('.tab.active')?.id === 'tab-pool' ? 'pool' : 'safe';
    switchTab(activeTab);
}

function renderSafeTips(tips) {
    if (!tips?.length) { document.getElementById('xp-container').innerHTML = '<p style="color:var(--text-muted)">No tips available.</p>'; return; }
    const top = tips[0];
    let html = `
        <div class="tip-top">
            <div>
                <div style="font-size:0.72rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">Top Pick</div>
                <div class="tip-top-score">${top.Tipp}</div>
            </div>
            <div class="tip-top-right">
                <div class="tip-top-xp">${top.xP.toFixed(2)} xP</div>
                <div class="tip-top-label">Expected Points</div>
            </div>
        </div>
    `;
    for (let i = 1; i < Math.min(4, tips.length); i++) {
        const t = tips[i];
        html += `
            <div class="tip-row">
                <span class="tip-rank">#${i+1}</span>
                <span class="tip-score">${t.Tipp}</span>
                <span class="tip-xp-val">${t.xP.toFixed(2)} xP</span>
            </div>
        `;
    }
    document.getElementById('xp-container').innerHTML = html;
}

function renderPoolTips(tips) {
    if (!tips?.length) { document.getElementById('pool-container').innerHTML = '<p style="color:var(--text-muted)">No pool tips available.</p>'; return; }
    const agg = parseFloat(document.getElementById('aggressiveness-slider').value);
    const top = tips[0];

    const edgeClass = top.edge_vs_field >= 0 ? 'positive' : 'negative';
    const edgeStr = top.edge_vs_field >= 0
        ? `+${top.edge_vs_field.toFixed(2)} pts vs field`
        : `${top.edge_vs_field.toFixed(2)} pts vs field`;

    let bannerText = '';
    if (agg === 0) bannerText = 'Set aggressiveness > 0 to see contrarian picks that differentiate you from the field.';
    else if (agg <= 0.3) bannerText = `Soft contrarian (λ=${agg}): same tendency as the field, different scoreline. Minimal xP cost, real differentiation.`;
    else if (agg <= 0.7) bannerText = `Contrarian mode (λ=${agg}): accepting lower average to get a ceiling above the field. Best when chasing.`;
    else bannerText = `High-risk mode (λ=${agg}): betting the field gets the result wrong. Use in KO phase when trailing badly.`;

    let html = `
        <div class="pool-mode-banner">${bannerText}</div>
        <div class="pool-top">
            <div class="pool-top-header">
                <div>
                    <div style="font-size:0.72rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">Pool Pick</div>
                    <div class="pool-top-score">${top.Tipp}</div>
                </div>
                <div class="pool-top-xp">${top.xP.toFixed(2)} xP</div>
            </div>
            <div class="pool-stats">
                <div class="pool-stat">
                    <span class="pool-stat-label">Edge vs field</span>
                    <span class="pool-stat-value ${edgeClass}">${edgeStr}</span>
                </div>
                <div class="pool-stat">
                    <span class="pool-stat-label">Upside (σ)</span>
                    <span class="pool-stat-value neutral">${top.upside.toFixed(2)}</span>
                </div>
            </div>
        </div>
    `;
    for (let i = 1; i < Math.min(4, tips.length); i++) {
        const t = tips[i];
        const ec = t.edge_vs_field >= 0 ? 'pos' : 'neg';
        const es = t.edge_vs_field >= 0 ? `+${t.edge_vs_field.toFixed(2)}` : t.edge_vs_field.toFixed(2);
        html += `
            <div class="pool-row">
                <span class="pool-row-score">${t.Tipp}</span>
                <span class="pool-row-xp">${t.xP.toFixed(2)} xP</span>
                <span class="pool-row-edge ${ec}">${es} edge</span>
            </div>
        `;
    }
    document.getElementById('pool-container').innerHTML = html;
}

// ── Tab switching ─────────────────────────────────────────────
function switchTab(tab) {
    document.getElementById('tab-safe').classList.toggle('active', tab === 'safe');
    document.getElementById('tab-pool').classList.toggle('active', tab === 'pool');
    document.getElementById('panel-safe').style.display = tab === 'safe' ? '' : 'none';
    document.getElementById('panel-pool').style.display = tab === 'pool' ? '' : 'none';
}

// ── Heatmap ───────────────────────────────────────────────────
function renderHeatmap(matchInfo, calc) {
    const container = document.getElementById('matrix-container');
    const maxP = calc.max_prob;

    // Column headers row
    let colHeaders = '<div class="axis-num col"></div>';
    for (let a = 0; a <= 5; a++) colHeaders += `<div class="axis-num col">${a}</div>`;

    let rowsHtml = '';
    for (let h = 0; h <= 5; h++) {
        let rowHtml = `<div class="axis-num">${h}</div>`;
        for (let a = 0; a <= 5; a++) {
            const prob = calc.matrix[h]?.[a] ?? 0;
            const bg = probColor(prob, maxP);
            const textColor = prob / maxP > 0.5 ? 'rgba(0,0,0,0.85)' : 'rgba(255,255,255,0.85)';
            const probPct = (prob * 100).toFixed(1) + '%';
            rowHtml += `
                <div class="heatmap-cell" style="background:${bg};color:${textColor}"
                     title="${matchInfo.home_disp} ${h}:${a} ${matchInfo.away_disp} — ${probPct}">
                    <span class="cell-pct">${probPct}</span>
                </div>`;
        }
        rowsHtml += `<div class="heatmap-row">${rowHtml}</div>`;
    }

    container.innerHTML = `
        <div class="heatmap-wrap">
            <div style="font-size:0.68rem;color:var(--text-muted);text-align:center;margin-bottom:4px;text-transform:uppercase;letter-spacing:1px;font-weight:700;">${matchInfo.away_disp} Goals →</div>
            <div class="heatmap-body">
                <div style="writing-mode:vertical-rl;transform:rotate(180deg);font-size:0.68rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:1px;font-weight:700;padding-right:8px;display:flex;align-items:center;justify-content:center;">
                    ${matchInfo.home_disp} Goals
                </div>
                <div>
                    <div class="heatmap-row">${colHeaders}</div>
                    ${rowsHtml}
                </div>
            </div>
        </div>
    `;
}

// ── Elo History ───────────────────────────────────────────────
async function loadEloHistoryView() {
    try {
        const history = await (await fetch('/api/elo_history')).json();
        const teams = Object.keys(history).sort();
        const sel = document.getElementById('history-team-selector');
        sel.innerHTML = teams.map(t => `<option value="${t}">${t}</option>`).join('');
        sel.onchange = () => renderEloChart(history, sel.value);
        if (teams.length) renderEloChart(history, teams[0]);
    } catch (e) {
        document.getElementById('elo-history-view').innerHTML += `<p style="color:var(--danger)">Error: ${e.message}</p>`;
    }
}

function renderEloChart(history, team) {
    const entries = history[team] || [];
    const labels = entries.map(e => e.match_id === 'baseline' ? 'Start' : `Match ${e.match_id}`);
    const data   = entries.map(e => e.elo);

    if (eloChartInstance) eloChartInstance.destroy();
    eloChartInstance = new Chart(document.getElementById('eloChart'), {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: `${team} Elo`,
                data,
                borderColor: '#c8901a',
                backgroundColor: 'rgba(200,144,26,0.08)',
                borderWidth: 2.5,
                pointRadius: 5,
                pointBackgroundColor: '#e6a51e',
                fill: true,
                tension: 0.3,
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { labels: { color: '#8899bb' } },
                tooltip: { backgroundColor: '#0f1e36', titleColor: '#f0f6ff', bodyColor: '#8899bb' }
            },
            scales: {
                x: { ticks: { color: '#4a5a7a' }, grid: { color: 'rgba(255,255,255,0.04)' } },
                y: { ticks: { color: '#4a5a7a' }, grid: { color: 'rgba(255,255,255,0.04)' } }
            }
        }
    });
}

// ── Performance Dashboard ─────────────────────────────────────
async function loadPerformanceView() {
    const grid = document.getElementById('performance-grid');
    grid.innerHTML = '';
    document.getElementById('kpi-matches').textContent = '…';
    document.getElementById('kpi-points').textContent  = '…';
    document.getElementById('kpi-hitrate').textContent = '…';

    let archiveData;
    try {
        archiveData = await (await fetch('/api/archive')).json();
    } catch (e) {
        grid.innerHTML = `<p style="color:var(--red)">Failed to load archive: ${e.message}</p>`;
        return;
    }

    let completedMatches = 0, totalPoints = 0, correctTendency = 0;

    Object.values(archiveData).forEach(match => {
        if (match.post_match_result?.status !== 'completed') return;

        completedMatches++;
        const pts = match.post_match_result.points_earned || 0;
        totalPoints += pts;
        if (pts >= 5) correctTendency++;

        const hasPrediction = match.prediction?.top_tip != null;
        const borderColor = !hasPrediction ? 'var(--text-3)'
            : pts >= 8 ? 'var(--green)'
            : pts >= 5 ? 'var(--amber)'
            : 'var(--red)';

        const tipLine = hasPrediction
            ? `<span style="font-size:1.15rem;font-weight:800;color:var(--text-1);">${match.prediction.top_tip}</span>
               <span style="font-size:0.82rem;color:var(--text-2);margin-left:10px;">Resultat: ${match.post_match_result.actual_score}</span>`
            : `<span style="font-size:0.82rem;color:var(--text-2);">Resultat: ${match.post_match_result.actual_score}</span>`;

        const ptsLine = hasPrediction
            ? `<div style="display:inline-block;background:rgba(255,255,255,0.05);color:${borderColor};
                           padding:3px 10px;border-radius:4px;font-weight:700;font-size:0.82rem;
                           border:1px solid ${borderColor}33;">+${pts} Punkte</div>`
            : `<div style="display:inline-block;color:var(--text-3);font-size:0.72rem;font-style:italic;">Kein Tipp erfasst</div>`;

        const card = document.createElement('div');
        card.className = 'glass-card';
        card.style.cssText = `border-left:4px solid ${borderColor};padding:16px 18px;`;
        card.innerHTML = `
            <div style="font-size:0.72rem;color:var(--text-2);margin-bottom:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                ${match.metadata.home_disp} vs ${match.metadata.away_disp}
            </div>
            <div style="margin-bottom:12px;">${tipLine}</div>
            ${ptsLine}
        `;
        grid.appendChild(card);
    });

    document.getElementById('kpi-matches').textContent = completedMatches;
    document.getElementById('kpi-points').textContent  = totalPoints;
    document.getElementById('kpi-hitrate').textContent = completedMatches > 0
        ? ((correctTendency / completedMatches) * 100).toFixed(1) + '%'
        : '0.0%';

    if (completedMatches === 0) {
        grid.innerHTML = `<p style="color:var(--text-2);font-size:0.85rem;">No completed matches yet. Run "Sync Elo Ratings" after matches finish.</p>`;
    }
}

// ── Helpers ───────────────────────────────────────────────────
function computeImpliedProbs(odds) {
    const rh = 1 / odds.home, rd = 1 / odds.draw, ra = 1 / odds.away;
    const t = rh + rd + ra;
    return { home: rh / t, draw: rd / t, away: ra / t };
}

function pct(p) { return (p * 100).toFixed(0) + '%'; }

function probColor(prob, maxProb) {
    if (!prob || !maxProb) return '#0d1220';
    const r = Math.min(prob / maxProb, 1);
    // Dark navy → deep amber → gold
    const stops = [
        [13,  18,  32],
        [90,  55,  10],
        [210, 148,  26],
    ];
    let c1, c2, t;
    if (r < 0.5) { c1 = stops[0]; c2 = stops[1]; t = r / 0.5; }
    else         { c1 = stops[1]; c2 = stops[2]; t = (r - 0.5) / 0.5; }
    const mix = (i) => Math.round(c1[i] + (c2[i] - c1[i]) * t);
    return `rgb(${mix(0)},${mix(1)},${mix(2)})`;
}
