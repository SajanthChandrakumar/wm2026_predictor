let currentMatches = [];
let selectedMatchId = null;
let lastCalcData = null;
let eloChartInstance = null;

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
    document.getElementById('nav-edge').addEventListener('click', () => {
        showView('edge');
        renderEdgeView(currentMatches);
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

    // Theme toggle
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        const savedTheme = localStorage.getItem('theme');
        if (savedTheme === 'light') {
            document.body.setAttribute('data-theme', 'light');
            themeToggle.checked = true;
        }
        themeToggle.addEventListener('change', (e) => {
            if (e.target.checked) {
                document.body.setAttribute('data-theme', 'light');
                localStorage.setItem('theme', 'light');
            } else {
                document.body.removeAttribute('data-theme');
                localStorage.setItem('theme', 'dark');
            }
            if (selectedMatchId) updatePrediction();
            if (eloChartInstance) loadEloHistoryView(); // redrawn chart
        });
    }

    // Back
    document.getElementById('back-btn').addEventListener('click', () => {
        selectedMatchId = null;
        showView('dashboard');
    });
}

// ── Views ─────────────────────────────────────────────────────
function showView(view) {
    ['matches-view', 'value-bets-view', 'edge-view', 'elo-history-view', 'performance-view', 'detail-view', 'loading-spinner']
        .forEach(id => document.getElementById(id).style.display = 'none');

    document.querySelectorAll('nav li').forEach(li => li.classList.remove('active'));

    const map = {
        'dashboard':   ['matches-view',      'nav-dashboard'],
        'value-bets':  ['value-bets-view',   'nav-value-bets'],
        'edge':        ['edge-view',         'nav-edge'],
        'elo-history': ['elo-history-view',  'nav-elo-history'],
        'performance': ['performance-view',  'nav-performance'],
        'detail':      ['detail-view',        null],
        'loading':     ['loading-spinner',    null],
    };
    const [viewId, navId] = map[view] || ['matches-view', 'nav-dashboard'];
    document.getElementById(viewId).style.display = '';
    if (navId) document.getElementById(navId).classList.add('active');
}

// ── API Calls ─────────────────────────────────────────────────
async function fetchQuota() {
    try {
        const data = await (await fetch('/api/quota')).json();
        const odds = data.odds || {};
        const fb = data.football || {};
        
        document.getElementById('quota-odds-value').textContent = odds.remaining ?? '--';
        document.getElementById('quota-odds-delta').textContent = `${odds.used ?? '?'} used`;
        
        document.getElementById('quota-fb-value').textContent = fb.remaining ?? '--';
        document.getElementById('quota-fb-delta').textContent = `${fb.used ?? '?'} used`;
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

    const homeFire = match.home_form?.on_fire ? '<span class="fire-badge" title="Team is on fire! 🔥">🔥</span>' : '';
    const awayFire = match.away_form?.on_fire ? '<span class="fire-badge" title="Team is on fire! 🔥">🔥</span>' : '';

    row.innerHTML = `
        <div class="fixture-time${isPast ? ' past' : ''}">${timeStr}</div>
        <div class="fixture-body">
            <div class="fixture-teams">
                <span class="fixture-home">${match.home_disp}${homeFire}</span>
                <div class="fix-bar">
                    <div class="bar-h" style="width:${hPct}%"></div>
                    <div class="bar-d" style="width:${dPct}%"></div>
                    <div class="bar-a" style="width:${aPct}%"></div>
                </div>
                <span class="fixture-away">${match.away_disp}${awayFire}</span>
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

function renderFormBlocks(formArray) {
    if (!formArray || formArray.length === 0) return '';
    const blocksHtml = formArray.map(f => {
        const cls = f.result === 'W' ? 'form-w' : f.result === 'D' ? 'form-d' : 'form-l';
        const title = `${f.result} vs ${f.opponent} (${f.score}) ${f.delta > 0 ? '+' : ''}${f.delta} Elo`;
        return `<span class="form-block ${cls}" title="${title}">${f.result}</span>`;
    }).join('');
    return `<div class="form-container">${blocksHtml}</div>`;
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

    if (matchInfo.h2h && matchInfo.home_team_id && matchInfo.away_team_id) {
        const h2h = matchInfo.h2h;
        const w1 = h2h[matchInfo.home_team_id] || 0;
        const w2 = h2h[matchInfo.away_team_id] || 0;
        const d = h2h.draws || 0;
        if (w1 > 0 || w2 > 0 || d > 0) {
            metaChips.push(`<span class="meta-chip">⚔️ H2H: ${w1}W - ${d}D - ${w2}L</span>`);
        }
    }

    document.getElementById('match-meta').innerHTML = metaChips.join('');

    // xG row
    const homeFire = matchInfo.home_form?.on_fire ? '<span class="fire-badge" title="Team is on fire! 🔥">🔥</span>' : '';
    const awayFire = matchInfo.away_form?.on_fire ? '<span class="fire-badge" title="Team is on fire! 🔥">🔥</span>' : '';

    const lineupDiffs = matchInfo.lineup_diff || {};
    let lineupAlertHtml = '';
    const homeDiff = lineupDiffs[matchInfo.home_team]?.missing || [];
    const awayDiff = lineupDiffs[matchInfo.away_team]?.missing || [];
    
    if (homeDiff.length > 0 || awayDiff.length > 0) {
        let msg = [];
        if (homeDiff.length > 0) msg.push(`<strong>${matchInfo.home_disp}</strong> missing: ${homeDiff.join(', ')}`);
        if (awayDiff.length > 0) msg.push(`<strong>${matchInfo.away_disp}</strong> missing: ${awayDiff.join(', ')}`);
        lineupAlertHtml = `<div class="lineup-alert">⚠️ <strong>Lineup Alert:</strong> ${msg.join(' | ')}</div>`;
    }

    document.getElementById('xg-row').innerHTML = `
        ${lineupAlertHtml}
        <div class="xg-team home">
            <span class="xg-team-name">${matchInfo.home_disp}${homeFire}</span>
            ${renderFormBlocks(matchInfo.home_form?.form)}
            <span class="xg-value">${calc.xg_home.toFixed(2)}</span>
            <span class="xg-label">Expected Goals</span>
        </div>
        <div class="xg-divider">
            <span>vs</span>
            <small>xG</small>
        </div>
        <div class="xg-team away">
            <span class="xg-team-name">${matchInfo.away_disp}${awayFire}</span>
            ${renderFormBlocks(matchInfo.away_form?.form)}
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

    renderSafeTips(calc.xp_tips);

    document.getElementById('adopt-tip-status').textContent = '';
    updateAdoptButton();
}

function currentActiveTip() {
    return lastCalcData?.xp_tips?.[0]?.Tipp ?? null;
}

function updateAdoptButton() {
    const btn = document.getElementById('adopt-tip-btn');
    if (!btn) return;
    const tip = currentActiveTip();
    btn.textContent = tip ? `Tipp übernehmen: ${tip}` : 'Tipp übernehmen';
    btn.disabled = !tip;
    btn.onclick = () => adoptCurrentTip();
}

async function adoptCurrentTip() {
    const tip = currentActiveTip();
    if (!tip || !selectedMatchId) return;
    const btn = document.getElementById('adopt-tip-btn');
    const status = document.getElementById('adopt-tip-status');
    btn.disabled = true;
    const prev = btn.textContent;
    btn.textContent = 'Speichere…';
    try {
        const res = await fetch('/api/archive/user_tip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ match_id: selectedMatchId, user_tip: tip })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Fehler');
        status.style.color = 'var(--green)';
        status.textContent = `✓ ${tip} als dein Tipp gespeichert`;
        btn.textContent = prev;
        btn.disabled = false;
    } catch (e) {
        status.style.color = 'var(--red)';
        status.textContent = `✗ ${e.message}`;
        btn.textContent = prev;
        btn.disabled = false;
    }
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

// ── Model Edge ────────────────────────────────────────────────
function renderEdgeView(matches) {
    const grid = document.getElementById('edge-grid');
    grid.innerHTML = '';
    const now = new Date();

    const rows = matches
        .filter(m => m.edge_home != null && new Date(m.raw_match.commence_time) > now)
        .sort((a, b) => Math.abs(b.edge_home) - Math.abs(a.edge_home));

    if (!rows.length) {
        grid.innerHTML = `<p style="color:var(--text-2);font-size:0.85rem;">Keine Edge-Daten verfügbar — Daten aktualisieren.</p>`;
        return;
    }

    rows.forEach(m => {
        const edgePts = m.edge_home * 100;
        const absEdge = Math.abs(edgePts);
        // Model favours home if edge > 0, away if < 0
        const favTeam = edgePts >= 0 ? m.home_disp : m.away_disp;
        const dir = edgePts >= 0 ? 'home' : 'away';
        const strength = absEdge >= 12 ? 'var(--green)' : absEdge >= 6 ? 'var(--amber)' : 'var(--text-3)';

        const mShare = (m.market_home_share * 100);
        const eShare = (m.elo_home_share * 100);

        const d = new Date(m.raw_match.commence_time);
        const when = d.toLocaleDateString('de-CH', { weekday: 'short', day: '2-digit', month: '2-digit', timeZone: 'Europe/Zurich' });

        const card = document.createElement('div');
        card.className = 'glass-card';
        card.style.cssText = `border-left:4px solid ${strength};padding:14px 18px;margin-bottom:10px;cursor:pointer;`;
        card.addEventListener('click', () => openMatch(m.id));
        card.innerHTML = `
            <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
                <div style="min-width:0;">
                    <div style="font-size:0.95rem;font-weight:800;color:var(--text-1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                        ${m.home_disp} <span style="color:var(--text-3);font-weight:600;">vs</span> ${m.away_disp}
                    </div>
                    <div style="font-size:0.68rem;color:var(--text-3);margin-top:2px;">${when}</div>
                </div>
                <div style="text-align:right;flex-shrink:0;">
                    <div style="font-size:1.2rem;font-weight:900;color:${strength};line-height:1;">
                        ${edgePts >= 0 ? '+' : ''}${edgePts.toFixed(1)}<span style="font-size:0.7rem;">pp</span>
                    </div>
                    <div style="font-size:0.62rem;color:var(--text-2);margin-top:3px;text-transform:uppercase;letter-spacing:0.5px;">
                        Elo favorisiert <strong style="color:var(--text-1);">${favTeam.replace(/^\S+\s/, '')}</strong>
                    </div>
                </div>
            </div>
            <div style="margin-top:12px;display:flex;flex-direction:column;gap:5px;">
                ${edgeBar('Markt', mShare, 'var(--blue)', m.home_disp, m.away_disp)}
                ${edgeBar('Elo',   eShare, 'var(--gold)', m.home_disp, m.away_disp)}
            </div>
        `;
        grid.appendChild(card);
    });
}

function edgeBar(label, homePct, color, homeDisp, awayDisp) {
    return `
        <div style="display:flex;align-items:center;gap:10px;">
            <span style="font-size:0.6rem;color:var(--text-3);font-weight:700;text-transform:uppercase;min-width:34px;">${label}</span>
            <span style="font-size:0.62rem;color:var(--text-2);min-width:30px;text-align:right;">${homePct.toFixed(0)}%</span>
            <div style="flex:1;height:7px;background:var(--surface-3);border-radius:4px;overflow:hidden;display:flex;">
                <div style="width:${homePct}%;height:100%;background:${color};"></div>
            </div>
            <span style="font-size:0.62rem;color:var(--text-2);min-width:30px;">${(100-homePct).toFixed(0)}%</span>
        </div>
    `;
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
    let algoTotal = 0, algoCorrectTendency = 0, algoMatchCount = 0;
    let hasReconstructed = false;

    // Bot accumulators: {botName: {pts, tipped, tendency}}
    const BOT_NAMES = ['chalk', 'odds_pure', 'elo_pure', 'draw_hunter', 'random', 'broker', 'professor', 'rebel', 'sniper', 'gambler'];
    const botStats = {};
    BOT_NAMES.forEach(b => { botStats[b] = { pts: 0, tipped: 0, tendency: 0 }; });

    Object.entries(archiveData).forEach(([match_id, match]) => {
        if (match.post_match_result?.status !== 'completed') return;

        completedMatches++;
        const pts = match.post_match_result.points_earned || 0;
        totalPoints += pts;
        if (pts >= 5) correctTendency++;

        const ap = match.post_match_result?.algo_points;
        if (ap != null) { algoTotal += ap; algoMatchCount++; if (ap >= 5) algoCorrectTendency++; }

        // Accumulate bot stats
        const botPoints = match.post_match_result?.bot_points ?? {};
        BOT_NAMES.forEach(bot => {
            const bp = botPoints[bot];
            if (bp != null) {
                botStats[bot].pts += bp;
                botStats[bot].tipped++;
                if (bp >= 5) botStats[bot].tendency++;
            }
        });

        const userTip  = match.prediction?.user_tip  ?? null;
        const algoTip  = match.prediction?.top_tip   ?? null;
        const algoPts  = match.post_match_result?.algo_points ?? null;
        const activeTip = userTip ?? algoTip;

        const borderColor = activeTip == null ? 'var(--text-3)'
            : pts >= 8 ? 'var(--green)'
            : pts >= 5 ? 'var(--amber)'
            : 'var(--red)';

        const algoColor = algoPts == null ? 'var(--text-3)'
            : algoPts >= 8 ? 'var(--green)'
            : algoPts >= 5 ? 'var(--amber)'
            : 'var(--red)';

        const myTipHtml = userTip
            ? `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                   <span style="font-size:0.62rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-3);font-weight:700;min-width:52px;">Mein Tipp</span>
                   <span style="font-size:1rem;font-weight:800;color:var(--text-1);">${userTip}</span>
                   <span style="margin-left:auto;font-size:0.78rem;font-weight:700;color:${borderColor};">+${pts} Pts</span>
                   <button onclick="editUserTip(this, '${match_id}')"
                       style="background:none;border:1px solid var(--border-2);border-radius:3px;
                              color:var(--text-3);font-size:0.65rem;padding:1px 6px;cursor:pointer;">✎</button>
               </div>`
            : `<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;" id="tip-input-${match_id}">
                   <span style="font-size:0.62rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-3);font-weight:700;min-width:52px;">Mein Tipp</span>
                   <input id="tip-val-${match_id}" type="text" placeholder="2:1" maxlength="5"
                       style="width:52px;background:var(--surface-2);border:1px solid var(--border-2);
                              border-radius:4px;color:var(--text-1);font-size:0.9rem;font-weight:700;
                              padding:3px 7px;text-align:center;outline:none;"
                       onclick="event.stopPropagation()">
                   <button onclick="saveUserTip(event,'${match_id}')"
                       style="background:var(--gold-dim);border:1px solid var(--gold-b);border-radius:4px;
                              color:var(--gold-l);font-size:0.72rem;font-weight:700;padding:3px 10px;cursor:pointer;">
                       Speichern
                   </button>
               </div>`;

        const isReconstructed = match.prediction?.algo_reconstructed === true;
        if (isReconstructed) hasReconstructed = true;
        const algoLabel = isReconstructed
            ? `<span style="font-size:0.62rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-3);font-weight:700;min-width:52px;" title="Aus Elo rekonstruiert — keine historischen Quoten verfügbar">Algo<span style="color:var(--amber);">*</span></span>`
            : `<span style="font-size:0.62rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-3);font-weight:700;min-width:52px;">Algo</span>`;

        const algoTipHtml = algoTip
            ? `<div style="display:flex;align-items:center;gap:8px;">
                   ${algoLabel}
                   <span style="font-size:1rem;font-weight:800;color:var(--text-2);">${algoTip}</span>
                   <span style="margin-left:auto;font-size:0.78rem;font-weight:700;color:${algoColor};">${algoPts != null ? '+'+algoPts+' Pts' : '–'}</span>
               </div>`
            : `<div style="display:flex;align-items:center;gap:8px;">
                   <span style="font-size:0.62rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-3);font-weight:700;min-width:52px;">Algo</span>
                   <span style="font-size:0.72rem;color:var(--text-3);font-style:italic;">Kein Algo-Tipp</span>
               </div>`;

        // Bot rows
        const BOT_SHORT = { chalk: 'Chalk', odds_pure: 'Odds', elo_pure: 'Elo', draw_hunter: 'Draw', random: 'Rnd', broker: 'Quoten', professor: 'Elo', rebel: 'Rebell', sniper: 'Sniper', gambler: 'Zocker' };
        const bots = match.prediction?.bots ?? {};
        const botPts = match.post_match_result?.bot_points ?? {};
        const botRowsHtml = Object.entries(bots).map(([bot, info]) => {
            const tip = info?.tip;
            if (!tip) return '';
            const bp = botPts[bot];
            const c = bp == null ? 'var(--text-3)' : bp >= 8 ? 'var(--green)' : bp >= 5 ? 'var(--amber)' : 'var(--red)';
            return `<div style="display:flex;align-items:center;gap:8px;">
                <span style="font-size:0.58rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-3);font-weight:600;min-width:52px;">${BOT_SHORT[bot] ?? bot}</span>
                <span style="font-size:0.9rem;font-weight:700;color:var(--text-3);">${tip}</span>
                <span style="margin-left:auto;font-size:0.72rem;font-weight:700;color:${c};">${bp != null ? '+'+bp+' Pts' : '–'}</span>
            </div>`;
        }).join('');

        const botsSection = botRowsHtml
            ? `<div style="border-top:1px solid var(--border);margin-top:6px;padding-top:6px;display:flex;flex-direction:column;gap:2px;">${botRowsHtml}</div>`
            : '';

        const card = document.createElement('div');
        card.className = 'glass-card';
        card.style.cssText = `border-left:4px solid ${borderColor};padding:14px 18px;`;
        card.innerHTML = `
            <div style="font-size:0.72rem;color:var(--text-2);margin-bottom:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                ${match.metadata.home_disp} vs ${match.metadata.away_disp}
                <span style="float:right;color:var(--text-3);">Resultat: <strong style="color:var(--text-1);">${match.post_match_result.actual_score}</strong></span>
            </div>
            <div style="border-top:1px solid var(--border);padding-top:10px;display:flex;flex-direction:column;gap:4px;">
                ${myTipHtml}
                ${algoTipHtml}
            </div>
            ${botsSection}
        `;
        grid.appendChild(card);
    });

    document.getElementById('kpi-matches').textContent = completedMatches;
    document.getElementById('kpi-points').textContent  = totalPoints;
    document.getElementById('kpi-hitrate').textContent = completedMatches > 0
        ? ((correctTendency / completedMatches) * 100).toFixed(1) + '%'
        : '0.0%';

    // ── You vs Algo Panel ────────────────────────────────────────
    const h2h = document.getElementById('h2h-panel');
    if (completedMatches === 0 || algoMatchCount === 0) {
        h2h.innerHTML = '';
    } else {
        const userHitRate  = ((correctTendency  / completedMatches) * 100).toFixed(1);
        const algoHitRate  = ((algoCorrectTendency / algoMatchCount) * 100).toFixed(1);
        const maxPts       = Math.max(totalPoints, algoTotal, 1);
        const userBarPct   = (totalPoints / maxPts * 100).toFixed(1);
        const algoBarPct   = (algoTotal   / maxPts * 100).toFixed(1);

        const diff         = totalPoints - algoTotal;
        const diffLabel    = diff > 0
            ? `<span style="color:var(--gold-l);font-weight:800;">Du führst +${diff} Pts</span>`
            : diff < 0
            ? `<span style="color:var(--blue);font-weight:800;">Algo führt +${Math.abs(diff)} Pts</span>`
            : `<span style="color:var(--text-2);font-weight:700;">Gleichstand</span>`;

        h2h.innerHTML = `
            <div class="glass-card" style="padding:20px 24px;">
                <div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:1.5px;
                            color:var(--text-3);font-weight:700;margin-bottom:16px;">You vs Algo</div>

                <div style="display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:20px;margin-bottom:16px;">
                    <!-- Du -->
                    <div>
                        <div style="font-size:0.72rem;color:var(--gold-l);font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">Du</div>
                        <div style="font-size:2.4rem;font-weight:900;color:var(--gold-l);line-height:1;letter-spacing:-1px;">${totalPoints}</div>
                        <div style="font-size:0.72rem;color:var(--text-2);margin-top:3px;">${userHitRate}% Tendenz</div>
                    </div>

                    <!-- Differenz -->
                    <div style="text-align:center;font-size:0.82rem;">${diffLabel}</div>

                    <!-- Algo -->
                    <div style="text-align:right;">
                        <div style="font-size:0.72rem;color:var(--blue);font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">Algo</div>
                        <div style="font-size:2.4rem;font-weight:900;color:var(--blue);line-height:1;letter-spacing:-1px;">${algoTotal}</div>
                        <div style="font-size:0.72rem;color:var(--text-2);margin-top:3px;">${algoHitRate}% Tendenz</div>
                    </div>
                </div>

                <!-- Progress bars -->
                <div style="display:flex;flex-direction:column;gap:6px;">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span style="font-size:0.62rem;color:var(--gold-l);font-weight:700;min-width:28px;text-align:right;">Du</span>
                        <div style="flex:1;height:8px;background:var(--surface-3);border-radius:4px;overflow:hidden;">
                            <div style="width:${userBarPct}%;height:100%;background:var(--gold);border-radius:4px;
                                        transition:width 0.6s ease;"></div>
                        </div>
                        <span style="font-size:0.72rem;color:var(--text-2);font-weight:600;min-width:36px;">${totalPoints} Pts</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span style="font-size:0.62rem;color:var(--blue);font-weight:700;min-width:28px;text-align:right;">Algo</span>
                        <div style="flex:1;height:8px;background:var(--surface-3);border-radius:4px;overflow:hidden;">
                            <div style="width:${algoBarPct}%;height:100%;background:var(--blue);border-radius:4px;
                                        transition:width 0.6s ease;"></div>
                        </div>
                        <span style="font-size:0.72rem;color:var(--text-2);font-weight:600;min-width:36px;">${algoTotal} Pts</span>
                    </div>
                </div>
            </div>
        `;
    }

    // ── Bot Scoreboard ────────────────────────────────────────────
    const botPanel = document.getElementById('bot-scoreboard');
    const BOT_COLORS = { chalk: 'var(--gold-l)', odds_pure: 'var(--green)', elo_pure: 'var(--blue)', draw_hunter: 'var(--amber)', random: 'var(--text-2)', broker: 'var(--blue)', professor: 'var(--green)', rebel: 'var(--amber)', sniper: 'var(--purple)', gambler: 'var(--text-2)' };

    const hasBotData = BOT_NAMES.some(b => botStats[b].tipped > 0);
    if (completedMatches > 0 && hasBotData) {
        // Build rows sorted by total pts desc
        const botRows = BOT_NAMES.filter(b => botStats[b].tipped > 0).map(b => {
            let displayName = '';
            if (b === 'broker') displayName = "💼 Der Broker (Quoten)";
            else if (b === 'professor') displayName = "🎓 Der Professor (Elo)";
            else if (b === 'rebel') displayName = "🔥 Der Rebell (Kontra-Feld)";
            else if (b === 'sniper') displayName = "🎯 Der X-Sniper (Draws)";
            else if (b === 'gambler') displayName = "🎲 Der Zocker (Zufall)";
            else displayName = b.charAt(0).toUpperCase() + b.slice(1);
            
            return {
                label: displayName, pts: botStats[b].pts, tipped: botStats[b].tipped,
                tendency: botStats[b].tendency, color: BOT_COLORS[b] || 'var(--text-3)', isUser: false
            };
        });
        
        const allRows = [
            { label: '★ Du (User)', pts: totalPoints, tipped: completedMatches, tendency: correctTendency, color: 'var(--gold-l)', isUser: true },
            ...botRows
        ].sort((a, b) => b.pts - a.pts);

        const rowsHtml = allRows.map((r, i) => {
            const avg = r.tipped > 0 ? (r.pts / r.tipped).toFixed(2) : '—';
            const tendPct = r.tipped > 0 ? ((r.tendency / r.tipped) * 100).toFixed(0) + '%' : '—';
            const rank = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `${i + 1}.`;
            return `<tr style="border-top:1px solid var(--border);">
                <td style="padding:9px 12px;font-size:0.8rem;font-weight:${r.isUser ? '800' : '600'};color:${r.color};">
                    <span style="color:var(--text-3);margin-right:6px;">${rank}</span>${r.label}
                </td>
                <td style="padding:9px 12px;text-align:right;font-size:0.9rem;font-weight:800;color:${r.color};">${r.pts}</td>
                <td style="padding:9px 12px;text-align:right;font-size:0.8rem;color:var(--text-2);">${r.tipped}</td>
                <td style="padding:9px 12px;text-align:right;font-size:0.8rem;color:var(--text-2);">${avg}</td>
                <td style="padding:9px 12px;text-align:right;font-size:0.8rem;color:var(--text-3);">${tendPct}</td>
            </tr>`;
        }).join('');

        botPanel.innerHTML = `
            <div class="glass-card" style="padding:20px 24px;">
                <div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--text-3);font-weight:700;margin-bottom:14px;">Bot Scoreboard</div>
                <table style="width:100%;border-collapse:collapse;">
                    <thead>
                        <tr>
                            <th style="padding:6px 12px;text-align:left;font-size:0.62rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-3);font-weight:700;">Bot</th>
                            <th style="padding:6px 12px;text-align:right;font-size:0.62rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-3);font-weight:700;">Pts</th>
                            <th style="padding:6px 12px;text-align:right;font-size:0.62rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-3);font-weight:700;">Tipped</th>
                            <th style="padding:6px 12px;text-align:right;font-size:0.62rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-3);font-weight:700;">Avg/Match</th>
                            <th style="padding:6px 12px;text-align:right;font-size:0.62rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-3);font-weight:700;">Tendency</th>
                        </tr>
                    </thead>
                    <tbody>${rowsHtml}</tbody>
                </table>
            </div>`;
    } else {
        botPanel.innerHTML = '';
    }

    if (completedMatches === 0) {
        grid.innerHTML = `<p style="color:var(--text-2);font-size:0.85rem;">No completed matches yet. Run "Sync Elo Ratings" after matches finish.</p>`;
    } else if (hasReconstructed) {
        const note = document.createElement('p');
        note.style.cssText = 'grid-column:1/-1;font-size:0.7rem;color:var(--text-3);margin-top:6px;font-style:italic;';
        note.innerHTML = '<span style="color:var(--amber);">*</span> Algo-Tipp aus Elo-Ratings rekonstruiert (Spiel vor App-Start, keine historischen Quoten verfügbar) — angenähert, nicht das volle Quoten-Modell.';
        grid.appendChild(note);
    }
}

async function saveUserTip(event, matchId) {
    event.stopPropagation();
    const input = document.getElementById(`tip-val-${matchId}`);
    const tip = input?.value?.trim();
    if (!tip || !/^\d+:\d+$/.test(tip)) {
        input.style.borderColor = 'var(--red)';
        return;
    }
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = '…';
    try {
        const res = await fetch('/api/archive/user_tip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ match_id: matchId, user_tip: tip })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Error');
        loadPerformanceView();  // reload to reflect new tip + points
    } catch (e) {
        btn.textContent = '✗';
        btn.style.color = 'var(--red)';
        setTimeout(() => { btn.textContent = 'Speichern'; btn.disabled = false; }, 2000);
    }
}

function editUserTip(btn, matchId) {
    const row = btn.closest('div');
    const currentTip = row.querySelector('span:nth-child(2)')?.textContent || '';
    row.innerHTML = `
        <span style="font-size:0.62rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-3);font-weight:700;min-width:52px;">Mein Tipp</span>
        <input id="tip-val-${matchId}" type="text" value="${currentTip}" maxlength="5"
            style="width:52px;background:var(--surface-2);border:1px solid var(--border-2);
                   border-radius:4px;color:var(--text-1);font-size:0.9rem;font-weight:700;
                   padding:3px 7px;text-align:center;outline:none;"
            onclick="event.stopPropagation()">
        <button onclick="saveUserTip(event,'${matchId}')"
            style="background:var(--gold-dim);border:1px solid var(--gold-b);border-radius:4px;
                   color:var(--gold-l);font-size:0.72rem;font-weight:700;padding:3px 10px;cursor:pointer;">
            Speichern
        </button>
    `;
}

// ── Helpers ───────────────────────────────────────────────────
function computeImpliedProbs(odds) {
    const rh = 1 / odds.home, rd = 1 / odds.draw, ra = 1 / odds.away;
    const t = rh + rd + ra;
    return { home: rh / t, draw: rd / t, away: ra / t };
}

function pct(p) { return (p * 100).toFixed(0) + '%'; }

function probColor(prob, maxProb) {
    const isLight = document.body.getAttribute('data-theme') === 'light';
    if (!prob || !maxProb) return isLight ? '#f5f0e6' : '#0d1220';
    const r = Math.min(prob / maxProb, 1);
    
    // Dark: Navy → deep amber → gold
    const darkStops = [
        [13,  18,  32],
        [90,  55,  10],
        [210, 148,  26],
    ];
    // Light: Beige → terracotta → dark orange
    const lightStops = [
        [245, 240, 230],
        [217, 140, 88],
        [200, 121, 65],
    ];
    const stops = isLight ? lightStops : darkStops;
    
    let c1, c2, t;
    if (r < 0.5) { c1 = stops[0]; c2 = stops[1]; t = r / 0.5; }
    else         { c1 = stops[1]; c2 = stops[2]; t = (r - 0.5) / 0.5; }
    const mix = (i) => Math.round(c1[i] + (c2[i] - c1[i]) * t);
    return `rgb(${mix(0)},${mix(1)},${mix(2)})`;
}
