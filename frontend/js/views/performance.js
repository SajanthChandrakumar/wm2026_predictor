// Performance Dashboard — KPIs, You-vs-Algo, Bot Scoreboard,
// Bot-Strategies info box, Bot-Points-Race chart, and match-history list
// with inline user-tip editing.

import { charts } from '../state.js';
import { api } from '../api.js?v=2';

// Canonical bot order. Includes legacy English names so old archive entries
// (from before the German reskinning) still aggregate cleanly.
const BOT_NAMES = ['chalk', 'odds_pure', 'elo_pure', 'draw_hunter', 'random',
                   'broker', 'professor', 'rebel', 'sniper', 'gambler'];

const BOT_COLORS = {
    chalk: 'var(--gold-l)', odds_pure: 'var(--green-l)', elo_pure: 'var(--blue-l)',
    draw_hunter: 'var(--amber-l)', random: 'var(--text-2)',
    broker: 'var(--blue-l)', professor: 'var(--green-l)', rebel: 'var(--amber-l)',
    sniper: 'var(--purple)', gambler: 'var(--text-2)',
};

const BOT_DISPLAY = {
    broker:    "Broker",
    professor: "Professor",
    rebel:     "Rebell",
    sniper:    "X-Sniper",
    gambler:   "Zocker",
};

const BOT_SHORT = {
    chalk: 'Chalk', odds_pure: 'Odds', elo_pure: 'Elo', draw_hunter: 'Draw', random: 'Rnd',
    broker: 'Quoten', professor: 'Elo', rebel: 'Rebell', sniper: 'Sniper', gambler: 'Zocker',
};

const ACTIVE_BOTS = ['broker', 'professor', 'rebel', 'sniper', 'gambler'];
const BOT_EMOJI   = { broker: '', professor: '', rebel: '', sniper: '', gambler: '' };
const BOT_LABEL   = { broker: 'Broker', professor: 'Prof.', rebel: 'Rebell', sniper: 'Sniper', gambler: 'Zocker' };

// User-designed "build-a-bot". Distinct cyan so it stands out from the house bots.
const CUSTOM_BOT_COLOR = 'var(--cyan-l, #2dd4bf)';
const CUSTOM_BOT_HEX   = '#2dd4bf';
const DEFAULT_BOT_PARAMS = { market_weight: 0.7, risk: 0.0, draw_bias: 0.0, underdog_bias: 0.0 };

// Race chart palette (separate from scoreboard colors — these are real hex
// values because Chart.js can't resolve CSS vars).
const BOT_RACE_META = {
    broker:    { name: 'Broker',    color: '#5b9bd5' },
    professor: { name: 'Professor', color: '#4caf82' },
    rebel:     { name: 'Rebell',    color: '#d9a441' },
    sniper:    { name: 'X-Sniper',  color: '#9b6dd1' },
    gambler:   { name: 'Zocker',    color: '#9a9a9a' },
};

export async function loadPerformanceView() {
    const grid = document.getElementById('performance-grid');
    grid.innerHTML = '';
    setKpi('…', '…', '…');

    let archive;
    try {
        archive = await api.archive();
    } catch (e) {
        grid.innerHTML = `<p style="color:var(--red-l)">Failed to load archive: ${e.message}</p>`;
        return;
    }

    // Single pass over the archive: aggregate stats + collect render data
    const totals = {
        completedMatches: 0, totalPoints: 0, correctTendency: 0,
        algoTotal: 0, algoCorrectTendency: 0, algoMatchCount: 0,
        hasReconstructed: false,
    };
    const botStats = {};
    BOT_NAMES.forEach(b => { botStats[b] = { pts: 0, tipped: 0, tendency: 0 }; });

    const completedMatches = [];

    Object.entries(archive).forEach(([matchId, match]) => {
        if (match.post_match_result?.status !== 'completed') return;

        totals.completedMatches++;
        const pts = match.post_match_result.points_earned || 0;
        totals.totalPoints += pts;
        if (pts >= 5) totals.correctTendency++;

        const ap = match.post_match_result?.algo_points;
        if (ap != null) {
            totals.algoTotal += ap; totals.algoMatchCount++;
            if (ap >= 5) totals.algoCorrectTendency++;
        }

        const botPoints = match.post_match_result?.bot_points ?? {};
        BOT_NAMES.forEach(bot => {
            const bp = botPoints[bot];
            if (bp != null) {
                botStats[bot].pts += bp;
                botStats[bot].tipped++;
                if (bp >= 5) botStats[bot].tendency++;
            }
        });

        if (match.prediction?.algo_reconstructed) totals.hasReconstructed = true;
        completedMatches.push([matchId, match, pts]);
    });

    // Saved build-a-bot (if any) — simulate it so it competes with full history
    // in the scoreboard and race, exactly like the house bots.
    let savedBot = null;
    try {
        const cb = await api.customBot();
        if (cb?.exists) {
            const sim = await api.simulateCustomBot(cb.params);
            savedBot = {
                name: cb.name || 'Mein Bot',
                params: cb.params,
                pts: sim.total_points,
                tipped: sim.matches,
                tendency: Math.round((sim.tendency_rate || 0) * sim.matches),
                pointsByMatch: Object.fromEntries(sim.breakdown.map(b => [b.match_id, b.points])),
            };
        }
    } catch (e) { /* custom bot is optional — ignore failures */ }

    renderKpis(totals);
    renderYouVsAlgo(totals);
    renderBotScoreboard(totals, botStats, savedBot);
    renderBuildABot(totals);

    // Bot-race uses chronological order (oldest match first)
    const chronological = [...completedMatches].sort((a, b) =>
        new Date(a[1].pre_match_snapshot?.timestamp_recorded || 0) -
        new Date(b[1].pre_match_snapshot?.timestamp_recorded || 0));
    renderBotRace(chronological, savedBot);

    if (totals.completedMatches === 0) {
        grid.innerHTML = `<p style="color:var(--text-2);font-size:var(--type-body);">No completed matches yet. Run "Sync Elo Ratings" after matches finish.</p>`;
        return;
    }

    // Sort match history newest first
    completedMatches.sort((a, b) =>
        new Date(b[1].pre_match_snapshot?.timestamp_recorded || 0) -
        new Date(a[1].pre_match_snapshot?.timestamp_recorded || 0));

    const listWrapper = document.createElement('div');
    listWrapper.className = 'glass-card static';
    listWrapper.style.cssText = 'padding:var(--sp-5);grid-column:1/-1;';

    // Header + filter row
    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--sp-4);gap:var(--sp-3);flex-wrap:wrap;';
    header.innerHTML = `
        <div class="section-title">Match History</div>
        <div class="match-history-filters">
            <select class="mh-filter-select">
                <option value="all">All</option>
                <option value="hit">✓ Hits</option>
                <option value="miss">✗ Missed</option>
                <option value="notipped">No tip</option>
            </select>
            <button data-filter="all" class="filter-btn active">All</button>
            <button data-filter="hit" class="filter-btn">✓ Hits</button>
            <button data-filter="miss" class="filter-btn">✗ Missed</button>
            <button data-filter="notipped" class="filter-btn">No tip</button>
        </div>`;
    listWrapper.appendChild(header);

    const matchList = document.createElement('div');
    matchList.className = 'match-history-list';

    completedMatches.forEach(([matchId, match, pts]) => {
        matchList.appendChild(buildMatchCard(matchId, match, pts));
    });
    listWrapper.appendChild(matchList);

    if (totals.hasReconstructed) {
        const note = document.createElement('p');
        note.style.cssText = 'font-size:var(--type-2xs);color:var(--text-3);margin-top:var(--sp-3);font-style:italic;';
        note.innerHTML = '<span style="color:var(--amber-l);">*</span> Algo tip reconstructed from Elo ratings — approximate, not the full odds model.';
        listWrapper.appendChild(note);
    }

    grid.appendChild(listWrapper);

    // Wire filter buttons + mobile select
    function applyFilter(filter) {
        listWrapper.querySelectorAll('[data-filter]').forEach(b => b.classList.toggle('active', b.dataset.filter === filter));
        listWrapper.querySelector('.mh-filter-select').value = filter;
        matchList.querySelectorAll('.match-card').forEach(card => {
            const rowPts = parseInt(card.dataset.pts ?? '0', 10);
            const hasTip = card.dataset.hastip === '1';
            const show =
                filter === 'all'      ? true :
                filter === 'hit'      ? (hasTip && rowPts >= 5) :
                filter === 'miss'     ? (hasTip && rowPts === 0) :
                filter === 'notipped' ? !hasTip : true;
            card.style.display = show ? '' : 'none';
        });
    }

    listWrapper.querySelectorAll('[data-filter]').forEach(btn =>
        btn.addEventListener('click', () => applyFilter(btn.dataset.filter)));
    listWrapper.querySelector('.mh-filter-select').addEventListener('change', e =>
        applyFilter(e.target.value));
}

function setKpi(matches, points, hitrate) {
    document.getElementById('kpi-matches').textContent = matches;
    document.getElementById('kpi-points').textContent  = points;
    document.getElementById('kpi-hitrate').textContent = hitrate;
}

function renderKpis(t) {
    setKpi(
        t.completedMatches,
        t.totalPoints,
        t.completedMatches > 0 ? ((t.correctTendency / t.completedMatches) * 100).toFixed(1) + '%' : '0.0%',
    );
}

function renderYouVsAlgo(t) {
    const panel = document.getElementById('h2h-panel');
    if (t.completedMatches === 0 || t.algoMatchCount === 0) { panel.innerHTML = ''; return; }

    const userHitRate = ((t.correctTendency / t.completedMatches) * 100).toFixed(1);
    const algoHitRate = ((t.algoCorrectTendency / t.algoMatchCount) * 100).toFixed(1);
    const maxPts = Math.max(t.totalPoints, t.algoTotal, 1);
    const userBarPct = (t.totalPoints / maxPts * 100).toFixed(1);
    const algoBarPct = (t.algoTotal   / maxPts * 100).toFixed(1);

    const diff = t.totalPoints - t.algoTotal;
    const diffLabel =
        diff > 0 ? `<span style="color:var(--gold-l);font-weight:800;">Du führst +${diff} Pts</span>` :
        diff < 0 ? `<span style="color:var(--blue-l);font-weight:800;">Algo führt +${Math.abs(diff)} Pts</span>` :
                   `<span style="color:var(--text-2);font-weight:700;">Gleichstand</span>`;

    panel.innerHTML = `
        <div class="glass-card static" style="padding:var(--sp-5);">
            <div class="section-title" style="margin-bottom:var(--sp-5);">You vs Algo</div>
            <div class="h2h-grid">
                <div class="h2h-stat">
                    <div class="h2h-stat-label" style="color:var(--gold-l);">Du</div>
                    <div class="h2h-stat-value" style="color:var(--gold-l);">${t.totalPoints}</div>
                    <div class="h2h-stat-sub">${userHitRate}% Tendenz</div>
                </div>
                <div class="h2h-center">${diffLabel}</div>
                <div class="h2h-stat" style="text-align:right;">
                    <div class="h2h-stat-label" style="color:var(--blue-l);">Algo</div>
                    <div class="h2h-stat-value" style="color:var(--blue-l);">${t.algoTotal}</div>
                    <div class="h2h-stat-sub">${algoHitRate}% Tendenz</div>
                </div>
            </div>
            <div style="display:flex;flex-direction:column;gap:var(--sp-2);">
                ${progressBar('Du', t.totalPoints, userBarPct, 'var(--gold-l)')}
                ${progressBar('Algo', t.algoTotal,  algoBarPct, 'var(--blue-l)')}
            </div>
        </div>`;
}

function progressBar(label, pts, widthPct, color) {
    return `
        <div style="display:flex;align-items:center;gap:var(--sp-2);">
            <span style="font-size:var(--type-2xs);color:${color};font-weight:700;min-width:32px;text-align:right;">${label}</span>
            <div class="progress-bar">
                <div class="progress-bar-fill" style="width:${widthPct}%;background:${color};"></div>
            </div>
            <span style="font-size:var(--type-xs);color:var(--text-2);font-weight:600;min-width:44px;">${pts} Pts</span>
        </div>`;
}

function renderBotScoreboard(t, botStats, savedBot = null) {
    const panel = document.getElementById('bot-scoreboard');
    const hasBotData = BOT_NAMES.some(b => botStats[b].tipped > 0);
    if (t.completedMatches === 0 || !hasBotData) { panel.innerHTML = ''; return; }

    const botRows = BOT_NAMES.filter(b => botStats[b].tipped > 0).map(b => ({
        label: BOT_DISPLAY[b] ?? b.charAt(0).toUpperCase() + b.slice(1),
        pts: botStats[b].pts, tipped: botStats[b].tipped,
        tendency: botStats[b].tendency,
        color: BOT_COLORS[b] || 'var(--text-3)', isUser: false,
    }));

    if (savedBot && savedBot.tipped > 0) {
        botRows.push({
            label: savedBot.name, pts: savedBot.pts, tipped: savedBot.tipped,
            tendency: savedBot.tendency, color: CUSTOM_BOT_COLOR, isUser: false, isCustom: true,
        });
    }

    const allRows = [
        { label: 'You', pts: t.totalPoints, tipped: t.completedMatches,
          tendency: t.correctTendency, color: 'var(--gold-l)', isUser: true },
        ...botRows,
    ].sort((a, b) => b.pts - a.pts);

    const rowsHtml = allRows.map((r, i) => {
        const avg = r.tipped > 0 ? (r.pts / r.tipped).toFixed(2) : '—';
        const tendPct = r.tipped > 0 ? ((r.tendency / r.tipped) * 100).toFixed(0) + '%' : '—';
        const rank = `${i + 1}.`;
        const userHighlight = r.isUser ? 'background:var(--gold-dim);'
                            : r.isCustom ? 'background:rgba(45,212,191,0.08);' : '';
        return `<tr style="border-top:1px solid var(--border);${userHighlight}">
            <td style="padding:var(--sp-2) var(--sp-3);font-size:var(--type-sm);font-weight:${r.isUser ? '800' : '600'};color:${r.color};">
                <span style="color:var(--text-3);margin-right:6px;">${rank}</span>${r.label}
            </td>
            <td class="text-right" style="padding:var(--sp-2) var(--sp-3);font-size:var(--type-body);font-weight:800;color:${r.color};">${r.pts}</td>
            <td class="text-right" style="padding:var(--sp-2) var(--sp-3);font-size:var(--type-sm);color:var(--text-2);">${r.tipped}</td>
            <td class="text-right" style="padding:var(--sp-2) var(--sp-3);font-size:var(--type-sm);color:var(--text-2);">${avg}</td>
            <td class="text-right" style="padding:var(--sp-2) var(--sp-3);font-size:var(--type-sm);color:var(--text-3);">${tendPct}</td>
        </tr>`;
    }).join('');

    panel.innerHTML = `
        <div class="glass-card static" style="padding:var(--sp-5);">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--sp-4);gap:var(--sp-3);">
                <div class="section-title">Bot Scoreboard</div>
                <button id="bot-strat-toggle" class="filter-btn" style="display:flex;align-items:center;gap:5px;">
                    <span>ⓘ</span> Wie funktionieren die Bots?
                </button>
            </div>
            <div style="overflow-x:auto;">
                <table class="data-table">
                    <thead>
                        <tr>${['Bot', 'Pts', 'Tipped', 'Avg/Match', 'Tendency'].map((h, i) =>
                            `<th class="${i === 0 ? '' : 'text-right'}">${h}</th>`
                        ).join('')}</tr>
                    </thead>
                    <tbody>${rowsHtml}</tbody>
                </table>
            </div>
            ${botStrategiesHtml()}
        </div>`;

    wireStratToggle();
}

function botStrategiesHtml() {
    const card = (icon, color, title, body) => `
        <div class="bot-strat-card">
            <div style="width:28px;height:28px;border-radius:50%;background:${color};color:var(--bg);display:flex;align-items:center;justify-content:center;font-size:0.7rem;font-weight:800;flex-shrink:0;">${icon}</div>
            <div>
                <div style="font-size:var(--type-sm);font-weight:800;color:${color};margin-bottom:3px;">${title}</div>
                <div style="font-size:0.74rem;color:var(--text-2);line-height:1.5;">${body}</div>
            </div>
        </div>`;

    return `
        <div id="bot-strategies" style="display:none;margin-top:var(--sp-5);padding-top:var(--sp-5);border-top:1px solid var(--border);">
            <div style="display:flex;flex-direction:column;gap:var(--sp-3);">
                ${card('A', 'var(--gold-l)', 'Algo &mdash; Das Haus-Modell',
                    '<b>70 % Buchmacher-Quoten + 30 % Elo-Ratings</b>, dann xG &rarr; Tor-für-Tor-Wahrscheinlichkeitsmatrix &rarr; der Tipp mit den meisten erwarteten Punkten (xP) gewinnt. Standardmodell der App. <i style="color:var(--text-3);">Verwendet in &bdquo;Top Tipp&ldquo; auf dem Dashboard.</i>')}
                ${card('B', 'var(--blue-l)', 'Broker &mdash; Pure Buchmacher-Quoten',
                    '<b>100 % Markt, 0 % Elo.</b> Vertraut blind den Buchmachern: berechnet xG nur aus den entmarginalisierten Quoten und wählt den Tipp mit höchstem xP. <i style="color:var(--text-3);">Die &bdquo;Weisheit der Crowd&ldquo;-Strategie.</i>')}
                ${card('P', 'var(--green-l)', 'Professor &mdash; Pure Elo-Ratings',
                    '<b>100 % Elo, 0 % Markt</b> (außer für Over/Under-Realismus). Ignoriert die Buchmacher komplett, leitet alles aus den Team-Stärken her. <i style="color:var(--text-3);">Schlägt den Markt, wenn die Quoten falsch liegen &mdash; verliert hart, wenn der Markt recht hat.</i>')}
                ${card('R', 'var(--amber-l)', 'Rebell &mdash; Kontra-Feld',
                    'Setzt <b>immer auf den Underdog</b>. Identifiziert das Team mit den schlechteren Quoten und wählt den besten Sieg-Tipp für genau dieses Team. <i style="color:var(--text-3);">Lebt von Überraschungen &mdash; selten Treffer, aber dann oft volle Punktzahl.</i>')}
                ${card('X', 'var(--purple)', 'X-Sniper &mdash; Draw-Spezialist',
                    'Tippt <b>immer ein Unentschieden</b>. Wählt aus den Unentschieden-Tipps (0:0, 1:1, 2:2 &hellip;) den mit dem höchsten xP. <i style="color:var(--text-3);">Hochrisiko-Strategie &mdash; trifft selten, aber wenn, dann oft volle 10 Punkte (exakter Score).</i>')}
                ${card('Z', 'var(--text-2)', 'Zocker &mdash; Gewichteter Zufall',
                    'Würfelt aus den <b>Top-10-Tipps</b> nach xP-Gewicht. Der wahrscheinlichste Tipp wird öfter gezogen als der zehntbeste. <i style="color:var(--text-3);">Match-ID als Seed &mdash; bei identischem Spiel kommt immer derselbe &bdquo;Zufall&ldquo; raus (reproduzierbar).</i>')}

                <div style="margin-top:var(--sp-2);padding:var(--sp-3);background:var(--surface);border-radius:var(--r);border:1px dashed var(--border);">
                    <div style="font-size:var(--type-xs);color:var(--text-3);line-height:1.6;">
                        <b style="color:var(--text-2);">Punkte-System (SRF Tippspiel):</b> Exakter Score = <b>10 Pt</b> &middot; Korrekte Tordifferenz = <b>8 Pt</b> &middot; Richtige Tendenz (Sieg/Niederlage/X) = <b>5 Pt</b> &middot; Falsch = <b>0 Pt</b>. In der K.O.-Phase verdoppeln sich die Punkte (×2).
                    </div>
                </div>
            </div>
        </div>`;
}

function wireStratToggle() {
    const btn = document.getElementById('bot-strat-toggle');
    const strat = document.getElementById('bot-strategies');
    if (!btn || !strat) return;
    btn.addEventListener('click', () => {
        const isOpen = strat.style.display !== 'none';
        strat.style.display = isOpen ? 'none' : 'block';
        btn.innerHTML = isOpen ? '<span>ⓘ</span> Wie funktionieren die Bots?' : '<span>✕</span> Schließen';
        if (!isOpen) {
            strat.closest('.glass-card')?.scrollTo?.({ top: strat.offsetTop - 80, behavior: 'smooth' });
        }
    });
}

// ── Match history card ──
function buildMatchCard(matchId, match, pts) {
    const userTip = match.prediction?.user_tip ?? null;
    const algoTip = match.prediction?.top_tip  ?? null;
    const algoPts = match.post_match_result?.algo_points ?? null;
    const isRecon = match.prediction?.algo_reconstructed === true;
    const hasTip  = userTip !== null;
    const actualScore = match.post_match_result.actual_score;

    const ptsBadge = p => {
        if (p == null) return `<span class="points-badge pts-na">–</span>`;
        const cls = p >= 10 ? 'pts-10' : p >= 8 ? 'pts-8' : p >= 5 ? 'pts-5' : 'pts-0';
        return `<span class="points-badge ${cls}">+${p}</span>`;
    };

    const ts = match.pre_match_snapshot?.timestamp_recorded;
    const dateStr = ts
        ? new Date(ts).toLocaleDateString('de-CH', { day: '2-digit', month: '2-digit' })
        : '—';

    const resultClass = !hasTip ? '' :
        pts >= 8 ? 'result-excellent' : pts >= 5 ? 'result-ok' : 'result-miss';

    const myCol = hasTip
        ? `<div class="mc-my-col">
               <span class="mc-my-label">My tip</span>
               <span class="mc-my-tip">${userTip}</span>
           </div>`
        : `<div class="mc-my-col"><span class="mc-no-tip">no tip</span></div>`;

    const botCells = buildBotCells(match, ptsBadge);

    const card = document.createElement('details');
    card.className = `match-card ${resultClass}`;
    card.dataset.pts    = pts;
    card.dataset.hastip = hasTip ? '1' : '0';

    card.innerHTML = `
        <summary class="match-card-summary">
            <div class="mc-date">${dateStr}</div>
            <div class="mc-teams">
                ${match.metadata.home_disp}
                <span style="color:var(--text-3);font-weight:400;"> vs </span>${match.metadata.away_disp}
            </div>
            <div class="mc-result">${actualScore}</div>
            ${myCol}
            <div class="mc-right">
                ${ptsBadge(hasTip ? pts : null)}
                <div class="mc-chevron">›</div>
            </div>
        </summary>
        <div class="match-card-body">
            <div class="mc-detail-cols">
                <div class="mc-detail-col">
                    <div class="mc-detail-label">My Tip</div>
                    <div id="tip-cell-${matchId}" class="mc-tip-input-row">${myTipCellHtml(matchId, userTip, hasTip)}</div>
                </div>
                <div class="mc-detail-col">
                    <div class="mc-detail-label">Algo${isRecon ? ' <sup style="color:var(--amber-l);">*</sup>' : ''}</div>
                    <div class="mc-detail-val">${algoTip || '–'}</div>
                </div>
                <div class="mc-detail-col">
                    <div class="mc-detail-label">Algo Pts</div>
                    <div>${ptsBadge(algoPts)}</div>
                </div>
            </div>
            ${botCells ? `<div class="mc-bots">${botCells}</div>` : ''}
        </div>`;

    return card;
}

function buildBotCells(match, ptsBadge) {
    const bots      = match.prediction?.bots ?? {};
    const botPoints = match.post_match_result?.bot_points ?? {};
    if (!ACTIVE_BOTS.some(b => bots[b]?.tip)) return '';

    return ACTIVE_BOTS.map(b => {
        const tip = bots[b]?.tip;
        if (!tip) return '';
        const pts   = botPoints[b] ?? null;
        const color = BOT_COLORS[b] || 'var(--text-3)';
        return `<div class="bot-tip-cell">
            <span style="color:${color};font-weight:700;white-space:nowrap;font-size:var(--type-2xs);">${BOT_EMOJI[b]} ${BOT_LABEL[b]}</span>
            <span style="font-size:var(--type-xs);font-weight:800;color:var(--text-1);">${tip}</span>
            ${ptsBadge(pts)}
        </div>`;
    }).join('');
}

function myTipCellHtml(matchId, userTip, hasTip) {
    if (hasTip) {
        return `<span style="font-size:var(--type-sm);font-weight:800;color:var(--text-1);">${userTip}</span>
                <button onclick="window.editUserTip(this,'${matchId}')"
                    title="Tipp bearbeiten"
                    style="background:none;border:1px solid var(--border-2);border-radius:var(--r-sm);color:var(--text-3);font-size:var(--type-2xs);padding:1px 5px;cursor:pointer;line-height:1.4;flex-shrink:0;">✎</button>`;
    }
    return `<input id="tip-val-${matchId}" type="text" placeholder="2:1" maxlength="5"
                class="select-field"
                style="width:46px;font-size:var(--type-sm);font-weight:700;padding:2px 5px;text-align:center;"
                onclick="event.stopPropagation()">
            <button onclick="window.saveUserTip(event,'${matchId}')"
                style="background:var(--gold-dim);border:1px solid var(--gold-b);border-radius:var(--r-sm);color:var(--gold-l);font-size:var(--type-2xs);font-weight:700;padding:2px 7px;cursor:pointer;white-space:nowrap;flex-shrink:0;">OK</button>`;
}

// ── Bot-Points-Race: cumulative points per bot over the played matches ──
function renderBotRace(completedSorted, savedBot = null) {
    const panel = document.getElementById('bot-race-panel');
    if (!panel) return;
    if (completedSorted.length < 2) {
        panel.innerHTML = '';
        if (charts.botRace) { charts.botRace.destroy(); charts.botRace = null; }
        return;
    }

    const activeBots = BOT_NAMES.filter(b => BOT_RACE_META[b] &&
        completedSorted.some(([, m]) => (m.post_match_result?.bot_points ?? {})[b] != null));

    const labels = completedSorted.map(([, m]) =>
        `${(m.metadata.home_team || '').slice(0, 3).toUpperCase()}–${(m.metadata.away_team || '').slice(0, 3).toUpperCase()}`);

    const running = {}; activeBots.forEach(b => running[b] = 0); let userRun = 0;
    const series  = {}; activeBots.forEach(b => series[b]  = []); const userSeries = [];
    // Custom bot accumulates by match_id (only matches it could simulate count).
    let customRun = 0; const customSeries = [];
    completedSorted.forEach(([mid, m]) => {
        const bp = m.post_match_result?.bot_points ?? {};
        activeBots.forEach(b => { running[b] += (bp[b] || 0); series[b].push(running[b]); });
        userRun += (m.post_match_result?.points_earned || 0); userSeries.push(userRun);
        if (savedBot) { customRun += (savedBot.pointsByMatch?.[mid] || 0); customSeries.push(customRun); }
    });

    const datasets = activeBots.map(b => ({
        label: BOT_RACE_META[b].name, data: series[b],
        borderColor: BOT_RACE_META[b].color, backgroundColor: BOT_RACE_META[b].color,
        tension: 0.3, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5,
    }));
    datasets.unshift({
        label: 'You', data: userSeries,
        borderColor: '#d4af37', backgroundColor: '#d4af37',
        tension: 0.3, borderWidth: 3, borderDash: [6, 3], pointRadius: 2, pointHoverRadius: 5,
    });
    if (savedBot && savedBot.tipped > 0) {
        datasets.push({
            label: savedBot.name, data: customSeries,
            borderColor: CUSTOM_BOT_HEX, backgroundColor: CUSTOM_BOT_HEX,
            tension: 0.3, borderWidth: 3, pointRadius: 2, pointHoverRadius: 5,
        });
    }

    panel.innerHTML = `
        <div class="glass-card static" style="padding:var(--sp-5);">
            <div class="section-title" style="margin-bottom:var(--sp-4);">Points Race</div>
            <div style="height:300px;"><canvas id="botRaceChart"></canvas></div>
        </div>`;

    const ctx = document.getElementById('botRaceChart').getContext('2d');
    if (charts.botRace) charts.botRace.destroy();
    const tick = getComputedStyle(document.documentElement).getPropertyValue('--text-3').trim() || '#888';
    charts.botRace = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { labels: { color: tick, boxWidth: 12, font: { size: 11 } } } },
            scales: {
                x: { ticks: { color: tick, maxRotation: 60, minRotation: 45, font: { size: 9 } }, grid: { display: false } },
                y: { beginAtZero: true, ticks: { color: tick }, grid: { color: 'rgba(255,255,255,0.05)' },
                     title: { display: true, text: 'Kumulierte Punkte', color: tick } },
            },
        },
    });
}

// ── Build-a-Bot: user-designed strategy with live what-if simulation ──
const _bob = { params: { ...DEFAULT_BOT_PARAMS }, name: 'Mein Bot', totals: null, timer: null };

function escapeAttr(s) {
    return String(s).replace(/[&<>"']/g, c =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function bobSliderHtml(key, label, min, max, step, value) {
    return `
        <div class="bob-slider">
            <div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;">
                <label style="font-size:var(--type-xs);font-weight:700;color:var(--text-1);">${label}</label>
                <span id="bob-val-${key}" style="font-size:var(--type-2xs);font-weight:700;color:${CUSTOM_BOT_COLOR};white-space:nowrap;"></span>
            </div>
            <input type="range" data-key="${key}" min="${min}" max="${max}" step="${step}" value="${value}"
                   style="width:100%;accent-color:${CUSTOM_BOT_HEX};">
        </div>`;
}

function bobSliderLabel(key, v) {
    if (key === 'market_weight') return `Markt ${Math.round(v * 100)}% · Elo ${Math.round((1 - v) * 100)}%`;
    if (key === 'risk') return v > 0 ? `Zocker +${v.toFixed(1)}` : v < 0 ? `Sicher ${v.toFixed(1)}` : 'Neutral';
    return v <= 0 ? 'aus' : `+${v.toFixed(1)}`;
}

function updateBobLabel(inp) {
    const el = document.getElementById(`bob-val-${inp.dataset.key}`);
    if (el) el.textContent = bobSliderLabel(inp.dataset.key, parseFloat(inp.value));
}

async function renderBuildABot(totals) {
    const panel = document.getElementById('build-a-bot-panel');
    if (!panel) return;
    if (totals.completedMatches === 0) { panel.innerHTML = ''; return; }
    _bob.totals = totals;

    // Prefill from the saved config if one exists
    try {
        const cb = await api.customBot();
        if (cb?.exists) {
            _bob.params = { ...DEFAULT_BOT_PARAMS, ...cb.params };
            _bob.name = cb.name || 'Mein Bot';
        }
    } catch { /* optional */ }

    const p = _bob.params;
    panel.innerHTML = `
        <div class="glass-card static" style="padding:var(--sp-5);">
            <div class="section-title" style="margin-bottom:6px;">Build Your Bot</div>
            <div style="font-size:var(--type-xs);color:var(--text-2);margin-bottom:var(--sp-4);line-height:1.5;">
                Stell deine eigene Tipp-Strategie ein und schau live, wie sie rückwirkend über alle bisherigen Spiele abgeschnitten hätte. <b style="color:${CUSTOM_BOT_COLOR};">Speichern</b> → dein Bot tritt dauerhaft im Scoreboard &amp; im Race gegen die Haus-Bots an.
            </div>
            <div class="bob-grid">
                ${bobSliderHtml('market_weight', 'Markt ↔ Elo', 0, 1, 0.05, p.market_weight)}
                ${bobSliderHtml('risk', 'Risiko', -1, 1, 0.1, p.risk)}
                ${bobSliderHtml('underdog_bias', 'Underdog-Bias', 0, 6, 0.5, p.underdog_bias)}
                ${bobSliderHtml('draw_bias', 'Unentschieden-Bias', 0, 6, 0.5, p.draw_bias)}
            </div>
            <div id="bob-result" style="margin-top:var(--sp-5);min-height:64px;"></div>
            <div style="display:flex;gap:var(--sp-3);align-items:center;margin-top:var(--sp-4);flex-wrap:wrap;">
                <input id="bob-name" type="text" maxlength="40" value="${escapeAttr(_bob.name)}" placeholder="Bot-Name"
                       class="select-field" style="flex:1;min-width:160px;font-size:var(--type-sm);padding:6px 10px;">
                <button id="bob-save" class="filter-btn"
                        style="background:rgba(45,212,191,0.12);border-color:${CUSTOM_BOT_HEX};color:${CUSTOM_BOT_COLOR};font-weight:700;padding:7px 16px;">Save Bot</button>
            </div>
        </div>`;

    panel.querySelectorAll('input[type=range]').forEach(inp => {
        updateBobLabel(inp);
        inp.addEventListener('input', () => {
            _bob.params[inp.dataset.key] = parseFloat(inp.value);
            updateBobLabel(inp);
            scheduleBobSim();
        });
    });
    panel.querySelector('#bob-name').addEventListener('input', e => { _bob.name = e.target.value; });
    panel.querySelector('#bob-save').addEventListener('click', saveBuildABot);

    runBobSim();
}

function scheduleBobSim() {
    clearTimeout(_bob.timer);
    _bob.timer = setTimeout(runBobSim, 300);
}

async function runBobSim() {
    const out = document.getElementById('bob-result');
    if (!out) return;
    out.innerHTML = `<span style="font-size:var(--type-sm);color:var(--text-3);">Rechne…</span>`;
    let sim;
    try {
        sim = await api.simulateCustomBot(_bob.params);
    } catch (e) {
        out.innerHTML = `<span style="font-size:var(--type-sm);color:var(--red-l);">Simulation fehlgeschlagen: ${e.message}</span>`;
        return;
    }
    const t = _bob.totals;
    const deltaUser = sim.total_points - t.totalPoints;
    const deltaAlgo = sim.total_points - t.algoTotal;
    const tendPct = (sim.tendency_rate * 100).toFixed(0);
    const chip = (label, diff) => {
        const color = diff > 0 ? 'var(--green-l)' : diff < 0 ? 'var(--red-l)' : 'var(--text-2)';
        const sign = diff > 0 ? '+' : '';
        return `<span style="font-size:var(--type-xs);color:var(--text-3);">vs ${label}</span>
                <span style="font-size:var(--type-sm);font-weight:800;color:${color};margin-right:var(--sp-3);">${sign}${diff}</span>`;
    };
    out.innerHTML = `
        <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;">
            <span style="font-size:var(--type-xs);color:var(--text-3);text-transform:uppercase;letter-spacing:1px;font-weight:700;">Hätte dein Bot</span>
            <span style="font-size:1.9rem;font-weight:800;color:${CUSTOM_BOT_COLOR};line-height:1;">${sim.total_points}</span>
            <span style="font-size:var(--type-sm);color:var(--text-2);">Punkte · ${tendPct}% Tendenz · ${sim.matches} Spiele</span>
        </div>
        <div style="margin-top:8px;">${chip('Du', deltaUser)} ${chip('Algo', deltaAlgo)}</div>`;
}

async function saveBuildABot() {
    const btn = document.getElementById('bob-save');
    if (!btn) return;
    btn.disabled = true;
    const prev = btn.textContent;
    btn.textContent = '…';
    try {
        await api.saveCustomBot({ name: _bob.name || 'Mein Bot', params: _bob.params });
        loadPerformanceView();  // reload so the bot shows up in scoreboard + race
    } catch (e) {
        btn.textContent = '✗ Fehler';
        btn.style.color = 'var(--red-l)';
        setTimeout(() => { btn.textContent = prev; btn.style.color = ''; btn.disabled = false; }, 2200);
    }
}

// ── User-tip editing — invoked from inline onclicks via window globals ──
export async function saveUserTip(event, matchId) {
    event.stopPropagation();
    const input = document.getElementById(`tip-val-${matchId}`);
    const tip = input?.value?.trim();
    if (!tip || !/^\d+:\d+$/.test(tip)) {
        if (input) input.style.borderColor = 'var(--red)';
        return;
    }
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = '…';
    try {
        await api.saveUserTip(matchId, tip);
        loadPerformanceView();  // reload to reflect new tip + points
    } catch {
        btn.textContent = '✗';
        btn.style.color = 'var(--red-l)';
        setTimeout(() => { btn.textContent = 'OK'; btn.disabled = false; }, 2000);
    }
}

export function editUserTip(btn, matchId) {
    const cell = document.getElementById(`tip-cell-${matchId}`);
    if (!cell) return;
    // Get current tip text from the span next to the edit button
    const currentTip = cell.querySelector('span')?.textContent?.trim() || '';
    cell.innerHTML = `
        <input id="tip-val-${matchId}" type="text" value="${currentTip}" maxlength="5"
            class="select-field"
            style="width:46px;font-size:var(--type-sm);font-weight:700;padding:2px 5px;text-align:center;"
            onclick="event.stopPropagation()">
        <button onclick="window.saveUserTip(event,'${matchId}')"
            style="background:var(--gold-dim);border:1px solid var(--gold-b);border-radius:var(--r-sm);color:var(--gold-l);font-size:var(--type-2xs);font-weight:700;padding:2px 7px;cursor:pointer;white-space:nowrap;flex-shrink:0;">OK</button>`;
    cell.querySelector('input')?.focus();
}
