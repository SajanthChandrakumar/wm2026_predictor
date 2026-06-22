// Performance Dashboard — KPIs, You-vs-Algo, Bot Scoreboard,
// Bot-Strategies info box, Bot-Points-Race chart, and match-history list
// with inline user-tip editing.

import { charts } from '../state.js';
import { api } from '../api.js';

// Canonical bot order. Includes legacy English names so old archive entries
// (from before the German reskinning) still aggregate cleanly.
const BOT_NAMES = ['chalk', 'odds_pure', 'elo_pure', 'draw_hunter', 'random',
                   'broker', 'professor', 'rebel', 'sniper', 'gambler'];

const BOT_COLORS = {
    chalk: 'var(--gold-l)', odds_pure: 'var(--green)', elo_pure: 'var(--blue)',
    draw_hunter: 'var(--amber)', random: 'var(--text-2)',
    broker: 'var(--blue)', professor: 'var(--green)', rebel: 'var(--amber)',
    sniper: 'var(--purple)', gambler: 'var(--text-2)',
};

const BOT_DISPLAY = {
    broker:    "💼 Der Broker (Quoten)",
    professor: "🎓 Der Professor (Elo)",
    rebel:     "🔥 Der Rebell (Kontra-Feld)",
    sniper:    "🎯 Der X-Sniper (Draws)",
    gambler:   "🎲 Der Zocker (Zufall)",
};

const BOT_SHORT = {
    chalk: 'Chalk', odds_pure: 'Odds', elo_pure: 'Elo', draw_hunter: 'Draw', random: 'Rnd',
    broker: 'Quoten', professor: 'Elo', rebel: 'Rebell', sniper: 'Sniper', gambler: 'Zocker',
};

// Race chart palette (separate from scoreboard colors — these are real hex
// values because Chart.js can't resolve CSS vars).
const BOT_RACE_META = {
    broker:    { name: '💼 Broker',    color: '#5b9bd5' },
    professor: { name: '🎓 Professor', color: '#4caf82' },
    rebel:     { name: '🔥 Rebell',    color: '#d9a441' },
    sniper:    { name: '🎯 X-Sniper',  color: '#9b6dd1' },
    gambler:   { name: '🎲 Zocker',    color: '#9a9a9a' },
};

export async function loadPerformanceView() {
    const grid = document.getElementById('performance-grid');
    grid.innerHTML = '';
    setKpi('…', '…', '…');

    let archive;
    try {
        archive = await api.archive();
    } catch (e) {
        grid.innerHTML = `<p style="color:var(--red)">Failed to load archive: ${e.message}</p>`;
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

    renderKpis(totals);
    renderYouVsAlgo(totals);
    renderBotScoreboard(totals, botStats);

    // Bot-race uses chronological order (oldest match first)
    const chronological = [...completedMatches].sort((a, b) =>
        new Date(a[1].pre_match_snapshot?.timestamp_recorded || 0) -
        new Date(b[1].pre_match_snapshot?.timestamp_recorded || 0));
    renderBotRace(chronological);

    if (totals.completedMatches === 0) {
        grid.innerHTML = `<p style="color:var(--text-2);font-size:0.85rem;">No completed matches yet. Run "Sync Elo Ratings" after matches finish.</p>`;
        return;
    }

    // Sort match history newest first
    completedMatches.sort((a, b) =>
        new Date(b[1].pre_match_snapshot?.timestamp_recorded || 0) -
        new Date(a[1].pre_match_snapshot?.timestamp_recorded || 0));

    const listWrapper = document.createElement('div');
    listWrapper.className = 'glass-card';
    listWrapper.style.cssText = 'padding:20px 24px;grid-column:1/-1;';

    // Header + filter row
    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;gap:12px;flex-wrap:wrap;';
    header.innerHTML = `
        <div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--text-3);font-weight:700;">
            Spielverlauf <span style="font-weight:500;opacity:0.7;">(neueste zuerst)</span>
        </div>
        <div style="display:flex;gap:6px;">
            <button data-filter="all"
                style="background:var(--surface-3);border:1px solid var(--border-2);color:var(--text-1);padding:3px 10px;border-radius:4px;font-size:0.68rem;font-weight:700;cursor:pointer;">
                Alle
            </button>
            <button data-filter="hit"
                style="background:var(--surface-2);border:1px solid var(--border-2);color:var(--text-2);padding:3px 10px;border-radius:4px;font-size:0.68rem;font-weight:600;cursor:pointer;">
                ✓ Treffer
            </button>
            <button data-filter="miss"
                style="background:var(--surface-2);border:1px solid var(--border-2);color:var(--text-2);padding:3px 10px;border-radius:4px;font-size:0.68rem;font-weight:600;cursor:pointer;">
                ✗ Verpasst
            </button>
            <button data-filter="notipped"
                style="background:var(--surface-2);border:1px solid var(--border-2);color:var(--text-2);padding:3px 10px;border-radius:4px;font-size:0.68rem;font-weight:600;cursor:pointer;">
                Kein Tipp
            </button>
        </div>`;
    listWrapper.appendChild(header);

    // Column header
    const colHeader = document.createElement('div');
    colHeader.style.cssText = 'display:grid;grid-template-columns:36px 1fr auto auto auto auto;gap:8px;padding:0 4px 8px 12px;border-bottom:2px solid var(--border);margin-bottom:2px;';
    ['Datum', 'Spiel · Ergebnis', 'Mein Tipp', 'Pts', 'Algo', 'Pts'].forEach((label, i) => {
        const th = document.createElement('div');
        th.style.cssText = `font-size:0.58rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-3);font-weight:700;text-align:${i >= 2 ? 'right' : 'left'};`;
        th.textContent = label;
        colHeader.appendChild(th);
    });
    listWrapper.appendChild(colHeader);

    const matchList = document.createElement('div');
    matchList.id = 'match-list';
    matchList.style.cssText = 'display:flex;flex-direction:column;';

    completedMatches.forEach(([matchId, match, pts]) => {
        matchList.appendChild(buildMatchRow(matchId, match, pts));
    });
    listWrapper.appendChild(matchList);

    if (totals.hasReconstructed) {
        const note = document.createElement('p');
        note.style.cssText = 'font-size:0.68rem;color:var(--text-3);margin-top:12px;font-style:italic;';
        note.innerHTML = '<span style="color:var(--amber);">*</span> Algo-Tipp aus Elo-Ratings rekonstruiert — angenähert, nicht das volle Quoten-Modell.';
        listWrapper.appendChild(note);
    }

    grid.appendChild(listWrapper);

    // Wire filter buttons
    listWrapper.querySelectorAll('[data-filter]').forEach(btn => {
        btn.addEventListener('click', () => {
            listWrapper.querySelectorAll('[data-filter]').forEach(b => {
                b.style.background = 'var(--surface-2)';
                b.style.color = 'var(--text-2)';
                b.style.fontWeight = '600';
            });
            btn.style.background = 'var(--surface-3)';
            btn.style.color = 'var(--text-1)';
            btn.style.fontWeight = '700';

            const filter = btn.dataset.filter;
            document.querySelectorAll('.match-row').forEach(row => {
                const rowPts  = parseInt(row.dataset.pts  ?? '0', 10);
                const hasTip  = row.dataset.hastip === '1';
                const show =
                    filter === 'all'      ? true :
                    filter === 'hit'      ? (hasTip && rowPts >= 5) :
                    filter === 'miss'     ? (hasTip && rowPts === 0) :
                    filter === 'notipped' ? !hasTip : true;
                row.style.display = show ? 'grid' : 'none';
            });
        });
    });
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
        diff < 0 ? `<span style="color:var(--blue);font-weight:800;">Algo führt +${Math.abs(diff)} Pts</span>` :
                   `<span style="color:var(--text-2);font-weight:700;">Gleichstand</span>`;

    panel.innerHTML = `
        <div class="glass-card" style="padding:20px 24px;">
            <div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--text-3);font-weight:700;margin-bottom:16px;">You vs Algo</div>
            <div style="display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:20px;margin-bottom:16px;">
                <div>
                    <div style="font-size:0.72rem;color:var(--gold-l);font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">Du</div>
                    <div style="font-size:2.4rem;font-weight:900;color:var(--gold-l);line-height:1;letter-spacing:-1px;">${t.totalPoints}</div>
                    <div style="font-size:0.72rem;color:var(--text-2);margin-top:3px;">${userHitRate}% Tendenz</div>
                </div>
                <div style="text-align:center;font-size:0.82rem;">${diffLabel}</div>
                <div style="text-align:right;">
                    <div style="font-size:0.72rem;color:var(--blue);font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">Algo</div>
                    <div style="font-size:2.4rem;font-weight:900;color:var(--blue);line-height:1;letter-spacing:-1px;">${t.algoTotal}</div>
                    <div style="font-size:0.72rem;color:var(--text-2);margin-top:3px;">${algoHitRate}% Tendenz</div>
                </div>
            </div>
            <div style="display:flex;flex-direction:column;gap:6px;">
                ${progressBar('Du', t.totalPoints, userBarPct, 'var(--gold-l)', 'var(--gold)')}
                ${progressBar('Algo', t.algoTotal,  algoBarPct, 'var(--blue)',  'var(--blue)')}
            </div>
        </div>`;
}

function progressBar(label, pts, widthPct, textColor, fillColor) {
    return `
        <div style="display:flex;align-items:center;gap:10px;">
            <span style="font-size:0.62rem;color:${textColor};font-weight:700;min-width:28px;text-align:right;">${label}</span>
            <div style="flex:1;height:8px;background:var(--surface-3);border-radius:4px;overflow:hidden;">
                <div style="width:${widthPct}%;height:100%;background:${fillColor};border-radius:4px;transition:width 0.6s ease;"></div>
            </div>
            <span style="font-size:0.72rem;color:var(--text-2);font-weight:600;min-width:36px;">${pts} Pts</span>
        </div>`;
}

function renderBotScoreboard(t, botStats) {
    const panel = document.getElementById('bot-scoreboard');
    const hasBotData = BOT_NAMES.some(b => botStats[b].tipped > 0);
    if (t.completedMatches === 0 || !hasBotData) { panel.innerHTML = ''; return; }

    const botRows = BOT_NAMES.filter(b => botStats[b].tipped > 0).map(b => ({
        label: BOT_DISPLAY[b] ?? b.charAt(0).toUpperCase() + b.slice(1),
        pts: botStats[b].pts, tipped: botStats[b].tipped,
        tendency: botStats[b].tendency,
        color: BOT_COLORS[b] || 'var(--text-3)', isUser: false,
    }));

    const allRows = [
        { label: '★ Du (User)', pts: t.totalPoints, tipped: t.completedMatches,
          tendency: t.correctTendency, color: 'var(--gold-l)', isUser: true },
        ...botRows,
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

    panel.innerHTML = `
        <div class="glass-card" style="padding:20px 24px;">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;gap:12px;">
                <div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--text-3);font-weight:700;">Bot Scoreboard</div>
                <button id="bot-strat-toggle"
                    style="background:var(--surface-2);border:1px solid var(--border-2);color:var(--text-2);
                           padding:4px 10px;border-radius:4px;font-size:0.68rem;font-weight:600;cursor:pointer;
                           display:flex;align-items:center;gap:5px;transition:all 0.15s;">
                    <span>ⓘ</span> Wie funktionieren die Bots?
                </button>
            </div>
            <table style="width:100%;border-collapse:collapse;">
                <thead>
                    <tr>${['Bot', 'Pts', 'Tipped', 'Avg/Match', 'Tendency'].map((h, i) =>
                        `<th style="padding:6px 12px;text-align:${i === 0 ? 'left' : 'right'};font-size:0.62rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-3);font-weight:700;">${h}</th>`
                    ).join('')}</tr>
                </thead>
                <tbody>${rowsHtml}</tbody>
            </table>
            ${botStrategiesHtml()}
        </div>`;

    wireStratToggle();
}

function botStrategiesHtml() {
    const card = (border, icon, color, title, body) => `
        <div style="display:grid;grid-template-columns:auto 1fr;gap:14px;align-items:start;padding:12px 14px;background:var(--surface-2);border:1px solid ${border};border-radius:6px;">
            <div style="font-size:1.4rem;line-height:1;">${icon}</div>
            <div>
                <div style="font-size:0.82rem;font-weight:800;color:${color};margin-bottom:3px;">${title}</div>
                <div style="font-size:0.74rem;color:var(--text-2);line-height:1.5;">${body}</div>
            </div>
        </div>`;

    return `
        <div id="bot-strategies" style="display:none;margin-top:18px;padding-top:18px;border-top:1px solid var(--border);">
            <div style="display:flex;flex-direction:column;gap:14px;">
                ${card('var(--gold-b)', '⚙️', 'var(--gold-l)', 'Algo &mdash; Das Haus-Modell',
                    '<b>70 % Buchmacher-Quoten + 30 % Elo-Ratings</b>, dann xG &rarr; Tor-für-Tor-Wahrscheinlichkeitsmatrix &rarr; der Tipp mit den meisten erwarteten Punkten (xP) gewinnt. Standardmodell der App. <i style="color:var(--text-3);">Verwendet in &bdquo;Top Tipp&ldquo; auf dem Dashboard.</i>')}
                ${card('var(--border)', '💼', 'var(--blue)', 'Der Broker &mdash; Pure Buchmacher-Quoten',
                    '<b>100 % Markt, 0 % Elo.</b> Vertraut blind den Buchmachern: berechnet xG nur aus den entmarginalisierten Quoten und wählt den Tipp mit höchstem xP. <i style="color:var(--text-3);">Die &bdquo;Weisheit der Crowd&ldquo;-Strategie.</i>')}
                ${card('var(--border)', '🎓', 'var(--green)', 'Der Professor &mdash; Pure Elo-Ratings',
                    '<b>100 % Elo, 0 % Markt</b> (außer für Over/Under-Realismus). Ignoriert die Buchmacher komplett, leitet alles aus den Team-Stärken her. <i style="color:var(--text-3);">Schlägt den Markt, wenn die Quoten falsch liegen &mdash; verliert hart, wenn der Markt recht hat.</i>')}
                ${card('var(--border)', '🔥', 'var(--amber)', 'Der Rebell &mdash; Kontra-Feld',
                    'Setzt <b>immer auf den Underdog</b>. Identifiziert das Team mit den schlechteren Quoten und wählt den besten Sieg-Tipp für genau dieses Team. <i style="color:var(--text-3);">Lebt von Überraschungen &mdash; selten Treffer, aber dann oft volle Punktzahl.</i>')}
                ${card('var(--border)', '🎯', 'var(--purple,#9b6dd1)', 'Der X-Sniper &mdash; Draw-Spezialist',
                    'Tippt <b>immer ein Unentschieden</b>. Wählt aus den Unentschieden-Tipps (0:0, 1:1, 2:2 &hellip;) den mit dem höchsten xP. <i style="color:var(--text-3);">Hochrisiko-Strategie &mdash; trifft selten, aber wenn, dann oft volle 10 Punkte (exakter Score).</i>')}
                ${card('var(--border)', '🎲', 'var(--text-2)', 'Der Zocker &mdash; Gewichteter Zufall',
                    'Würfelt aus den <b>Top-10-Tipps</b> nach xP-Gewicht. Der wahrscheinlichste Tipp wird öfter gezogen als der zehntbeste. <i style="color:var(--text-3);">Match-ID als Seed &mdash; bei identischem Spiel kommt immer derselbe &bdquo;Zufall&ldquo; raus (reproduzierbar).</i>')}

                <div style="margin-top:6px;padding:10px 14px;background:var(--surface);border-radius:6px;border:1px dashed var(--border);">
                    <div style="font-size:0.7rem;color:var(--text-3);line-height:1.6;">
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
        if (!isOpen) strat.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
}

// ── Compact match row ──
function buildMatchRow(matchId, match, pts) {
    const userTip = match.prediction?.user_tip ?? null;
    const algoTip = match.prediction?.top_tip  ?? null;
    const algoPts = match.post_match_result?.algo_points ?? null;
    const isRecon = match.prediction?.algo_reconstructed === true;
    const hasTip  = userTip !== null;

    const ptsBadge = p => {
        if (p == null) return `<span style="color:var(--text-3);font-size:0.7rem;min-width:32px;display:inline-block;text-align:right;">–</span>`;
        const [color, bg] =
            p >= 10 ? ['#4caf82', 'rgba(76,175,130,0.18)'] :
            p >= 8  ? ['#4caf82', 'rgba(76,175,130,0.12)'] :
            p >= 5  ? ['#d9a441', 'rgba(217,164,65,0.18)'] :
                      ['#e05555', 'rgba(220,80,80,0.14)'];
        return `<span style="font-size:0.72rem;font-weight:800;color:${color};background:${bg};padding:1px 6px;border-radius:3px;white-space:nowrap;min-width:32px;display:inline-block;text-align:center;">+${p}</span>`;
    };

    const ts = match.pre_match_snapshot?.timestamp_recorded;
    const dateStr = ts
        ? new Date(ts).toLocaleDateString('de-CH', { day: '2-digit', month: '2-digit' })
        : '—';

    const borderColor = !hasTip ? 'var(--border)' :
        pts >= 8 ? '#4caf82' : pts >= 5 ? '#d9a441' : '#e05555';

    const row = document.createElement('div');
    row.className = 'match-row';
    row.dataset.pts    = pts;
    row.dataset.hastip = hasTip ? '1' : '0';
    row.style.cssText = `
        display:grid;
        grid-template-columns:36px 1fr auto auto auto auto;
        align-items:center;
        gap:8px;
        padding:8px 4px 8px 10px;
        border-bottom:1px solid var(--border);
        border-left:3px solid ${borderColor};
    `;

    const dateEl = document.createElement('div');
    dateEl.style.cssText = 'font-size:0.6rem;color:var(--text-3);white-space:nowrap;line-height:1.3;text-align:center;';
    dateEl.textContent = dateStr;

    const nameEl = document.createElement('div');
    nameEl.style.cssText = 'font-size:0.78rem;font-weight:600;color:var(--text-1);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;';
    nameEl.innerHTML = `${match.metadata.home_disp} <span style="color:var(--text-3);font-weight:400;">vs</span> ${match.metadata.away_disp}
        <span style="color:var(--text-3);font-weight:500;font-size:0.72rem;"> · ${match.post_match_result.actual_score}</span>`;

    const myTipEl = document.createElement('div');
    myTipEl.id = `tip-cell-${matchId}`;
    myTipEl.style.cssText = 'display:flex;align-items:center;gap:5px;justify-content:flex-end;';
    myTipEl.innerHTML = myTipCellHtml(matchId, userTip, hasTip);

    const myPtsEl = document.createElement('div');
    myPtsEl.style.cssText = 'text-align:right;min-width:38px;';
    myPtsEl.innerHTML = hasTip ? ptsBadge(pts) : `<span style="color:var(--text-3);font-size:0.7rem;">–</span>`;

    const algoEl = document.createElement('div');
    algoEl.style.cssText = 'display:flex;align-items:center;gap:4px;justify-content:flex-end;';
    algoEl.innerHTML = algoTip
        ? `<span style="font-size:0.6rem;color:var(--text-3);font-weight:600;white-space:nowrap;">Algo</span>
           <span style="font-size:0.78rem;font-weight:700;color:var(--text-2);">${algoTip}${isRecon ? '<sup style="color:#d9a441;font-size:0.55rem;">*</sup>' : ''}</span>`
        : `<span style="font-size:0.65rem;color:var(--text-3);font-style:italic;">–</span>`;

    const algoPtsEl = document.createElement('div');
    algoPtsEl.style.cssText = 'text-align:right;min-width:38px;';
    algoPtsEl.innerHTML = ptsBadge(algoPts);

    row.appendChild(dateEl);
    row.appendChild(nameEl);
    row.appendChild(myTipEl);
    row.appendChild(myPtsEl);
    row.appendChild(algoEl);
    row.appendChild(algoPtsEl);
    return row;
}

function myTipCellHtml(matchId, userTip, hasTip) {
    if (hasTip) {
        return `<span style="font-size:0.82rem;font-weight:800;color:var(--text-1);">${userTip}</span>
                <button onclick="window.editUserTip(this,'${matchId}')"
                    title="Tipp bearbeiten"
                    style="background:none;border:1px solid var(--border-2);border-radius:3px;color:var(--text-3);font-size:0.6rem;padding:1px 5px;cursor:pointer;line-height:1.4;flex-shrink:0;">✎</button>`;
    }
    return `<input id="tip-val-${matchId}" type="text" placeholder="2:1" maxlength="5"
                style="width:46px;background:var(--surface-2);border:1px solid var(--border-2);border-radius:4px;color:var(--text-1);font-size:0.82rem;font-weight:700;padding:2px 5px;text-align:center;outline:none;"
                onclick="event.stopPropagation()">
            <button onclick="window.saveUserTip(event,'${matchId}')"
                style="background:var(--gold-dim);border:1px solid var(--gold-b);border-radius:4px;color:var(--gold-l);font-size:0.66rem;font-weight:700;padding:2px 7px;cursor:pointer;white-space:nowrap;flex-shrink:0;">OK</button>`;
}

// ── Bot-Points-Race: cumulative points per bot over the played matches ──
function renderBotRace(completedSorted) {
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
    completedSorted.forEach(([, m]) => {
        const bp = m.post_match_result?.bot_points ?? {};
        activeBots.forEach(b => { running[b] += (bp[b] || 0); series[b].push(running[b]); });
        userRun += (m.post_match_result?.points_earned || 0); userSeries.push(userRun);
    });

    const datasets = activeBots.map(b => ({
        label: BOT_RACE_META[b].name, data: series[b],
        borderColor: BOT_RACE_META[b].color, backgroundColor: BOT_RACE_META[b].color,
        tension: 0.3, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5,
    }));
    datasets.unshift({
        label: '★ Du', data: userSeries,
        borderColor: '#d4af37', backgroundColor: '#d4af37',
        tension: 0.3, borderWidth: 3, borderDash: [6, 3], pointRadius: 2, pointHoverRadius: 5,
    });

    panel.innerHTML = `
        <div class="glass-card" style="padding:20px 24px;">
            <div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--text-3);font-weight:700;margin-bottom:14px;">🏁 Bot-Points-Race</div>
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
        btn.style.color = 'var(--red)';
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
            style="width:46px;background:var(--surface-2);border:1px solid var(--border-2);border-radius:4px;color:var(--text-1);font-size:0.82rem;font-weight:700;padding:2px 5px;text-align:center;outline:none;"
            onclick="event.stopPropagation()">
        <button onclick="window.saveUserTip(event,'${matchId}')"
            style="background:var(--gold-dim);border:1px solid var(--gold-b);border-radius:4px;color:var(--gold-l);font-size:0.66rem;font-weight:700;padding:2px 7px;cursor:pointer;white-space:nowrap;flex-shrink:0;">OK</button>`;
    cell.querySelector('input')?.focus();
}
