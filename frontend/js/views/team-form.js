// Team Form view — Power Rankings (sortable table of all teams) +
// Multi-team Elo comparison chart with archive-derived opponent labels.

import { teamForm, charts } from '../state.js';
import { api } from '../api.js?v=2';
import { normTeam } from '../util.js';

// Chart line colors, rotated per selected team.
const COMPARE_COLORS = ['#d4af37', '#5b9bd5', '#4caf82', '#d9a441', '#9b6dd1', '#d9645b', '#7ec8e3', '#c4b283'];

export async function loadTeamFormView() {
    try {
        const [history, archive, ratings] = await Promise.all([
            api.eloHistory(), api.archive(), api.eloRatings(),
        ]);

        // elo_ratings.csv is the authoritative current Elo + complete team list.
        // elo_history.json only has teams whose Elo changed — teams like Argentina
        // / France that haven't been touched yet are missing. Seed them here.
        Object.entries(ratings).forEach(([team, info]) => {
            if (!history[team]) {
                history[team] = [{ timestamp: 0, match_id: 'baseline', elo: info.elo }];
            } else {
                const last = history[team][history[team].length - 1];
                if (Math.abs(last.elo - info.elo) > 0.5) {
                    history[team].push({ timestamp: Date.now() / 1000, match_id: 'sync', elo: info.elo });
                }
            }
        });

        // Per-team match log derived from archive — opponent, score, result.
        // Used both for W-D-L badges and for the compare-chart tooltip.
        const matchInfo = {};
        Object.entries(archive).forEach(([mid, m]) => {
            const pmr = m.post_match_result;
            if (pmr?.status !== 'completed' || !pmr.actual_score) return;
            const home = normTeam(m.metadata.home_team);
            const away = normTeam(m.metadata.away_team);
            const [hs, as] = pmr.actual_score.split(':').map(Number);
            if (Number.isNaN(hs) || Number.isNaN(as)) return;

            const ts = m.pre_match_snapshot?.timestamp_recorded || '';
            (matchInfo[home] ||= {})[mid] = { opponent: away, score: pmr.actual_score, result: hs > as ? 'W' : hs < as ? 'L' : 'D', ts };
            (matchInfo[away] ||= {})[mid] = { opponent: home, score: `${as}:${hs}`,    result: hs < as ? 'W' : hs > as ? 'L' : 'D', ts };
        });

        teamForm.history = history;
        teamForm.matchInfo = matchInfo;

        // Default selection: top 4 by current Elo
        if (teamForm.selected.size === 0) {
            computeRankings().slice(0, 4).forEach(r => teamForm.selected.add(r.team));
        }

        renderPowerRankings();
        renderTeamSelector();
        renderCompareChart();
    } catch (e) {
        document.getElementById('elo-history-view').insertAdjacentHTML('beforeend',
            `<p style="color:var(--red-l);font-size:var(--type-body);">Fehler: ${e.message}</p>`);
    }
}

function computeRankings() {
    return Object.entries(teamForm.history).map(([team, entries]) => {
        const sorted = [...entries].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
        const base = sorted[0]?.elo ?? 1500;
        const curr = sorted[sorted.length - 1]?.elo ?? base;
        const played = Object.values(teamForm.matchInfo[team] || {})
            .sort((a, b) => (a.ts || '').localeCompare(b.ts || ''));
        const w = played.filter(p => p.result === 'W').length;
        const d = played.filter(p => p.result === 'D').length;
        const l = played.filter(p => p.result === 'L').length;
        const form = played.slice(-5).map(p => p.result);  // last 5
        return { team, elo: curr, delta: curr - base, w, d, l, form };
    }).sort((a, b) => b.elo - a.elo);
}

function renderPowerRankings() {
    const panel = document.getElementById('power-rankings-panel');
    const rows = computeRankings();

    const rowsHtml = rows.map((r, i) => {
        const dColor = r.delta > 0 ? 'var(--green-l)' : r.delta < 0 ? 'var(--red-l)' : 'var(--text-3)';
        const dSign  = r.delta > 0 ? '▲' : r.delta < 0 ? '▼' : '·';
        const formHtml = r.form.length
            ? r.form.map(x => {
                const cls = x === 'W' ? 'w' : x === 'D' ? 'd' : 'l';
                return `<span class="form-badge-sm ${cls}">${x}</span>`;
            }).join(' ')
            : `<span style="font-size:var(--type-2xs);color:var(--text-3);font-style:italic;">noch nicht gespielt</span>`;
        const isSelected = teamForm.selected.has(r.team);
        const rankDisplay = i + 1;
        const rankColor = i < 3 ? 'var(--text-1)' : 'var(--text-3)';
        const bg = isSelected ? 'var(--gold-dim)' : 'transparent';

        return `<tr data-team="${r.team}"
                    style="cursor:pointer;background:${bg};transition:background 0.15s;"
                    onclick="window.toggleTeamSelect('${escapeJs(r.team)}')"
                    onmouseover="this.style.background='var(--surface-2)'"
                    onmouseout="this.style.background='${bg}'">
            <td class="text-center" style="padding:var(--sp-2) var(--sp-3);font-size:var(--type-sm);font-weight:800;color:${rankColor};">${rankDisplay}</td>
            <td style="padding:var(--sp-2) var(--sp-2);font-size:var(--type-body);font-weight:700;color:var(--text-1);white-space:nowrap;">
                ${r.team}
            </td>
            <td class="text-right" style="padding:var(--sp-2) var(--sp-3);font-size:var(--type-body);font-weight:800;color:var(--text-1);">${r.elo.toFixed(0)}</td>
            <td class="text-right" style="padding:var(--sp-2) var(--sp-3);font-size:var(--type-sm);font-weight:700;color:${dColor};">${dSign} ${Math.abs(r.delta).toFixed(0)}</td>
            <td class="text-center" style="padding:var(--sp-2) var(--sp-3);font-size:var(--type-xs);color:var(--text-2);">
                <span style="color:var(--green-l);">${r.w}</span>-<span style="color:var(--amber-l);">${r.d}</span>-<span style="color:var(--red-l);">${r.l}</span>
            </td>
            <td style="padding:var(--sp-2) var(--sp-3);font-size:var(--type-xs);display:flex;gap:3px;align-items:center;">${formHtml}</td>
        </tr>`;
    }).join('');

    panel.innerHTML = `
        <div class="glass-card static" style="padding:var(--sp-5);">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--sp-4);gap:var(--sp-3);">
                <div>
                    <div class="section-title" style="margin-bottom:2px;">Power Rankings</div>
                    <div class="section-subtitle">Sorted by current Elo · Click a row to compare in chart</div>
                </div>
                <div style="font-size:var(--type-xs);color:var(--text-3);">${rows.length} Teams</div>
            </div>
            <div style="max-height:520px;overflow-y:auto;border-radius:var(--r-sm);">
                <table class="data-table">
                    <thead>
                        <tr>${['#', 'Team', 'Elo', 'Δ Start', 'W-D-L', 'Form'].map((h, i) =>
                            `<th class="${[0, 4].includes(i) ? 'text-center' : [2, 3].includes(i) ? 'text-right' : ''}">${h}</th>`
                        ).join('')}</tr>
                    </thead>
                    <tbody>${rowsHtml}</tbody>
                </table>
            </div>
            <div style="margin-top:var(--sp-4);padding:var(--sp-3) var(--sp-4);background:var(--surface-2);border:1px solid var(--border);border-radius:var(--r-sm);display:flex;gap:var(--sp-3);align-items:flex-start;">
                <span style="font-size:var(--type-xs);flex-shrink:0;margin-top:1px;color:var(--accent);font-weight:800;">+80</span>
                <div style="font-size:var(--type-xs);color:var(--text-2);line-height:1.6;">
                    <strong style="color:var(--text-1);">Host nation bonus:</strong>
                    <span style="color:var(--gold-l);font-weight:700;">USA · Canada · Mexico</span>
                    receive a <strong style="color:var(--gold-l);">+80 Elo boost</strong> applied after each match they play — reflecting the well-documented home-crowd advantage in international football. This bonus accumulates over the tournament and is baked into all probability calculations.
                </div>
            </div>
        </div>`;
}

// Toggle a team in/out of the compare selection. Cap at 4 — pops oldest if full.
export function toggleTeamSelect(team) {
    const sel = teamForm.selected;
    if (sel.has(team)) sel.delete(team);
    else {
        if (sel.size >= 4) sel.delete([...sel][0]);  // FIFO pop
        sel.add(team);
    }
    renderPowerRankings();
    renderTeamSelector();
    renderCompareChart();
}

function renderTeamSelector() {
    const grid = document.getElementById('team-compare-grid');
    if (!grid) return;

    const teams = Object.keys(teamForm.history).sort();
    const filter = teamForm.search.toLowerCase();
    const visible = filter ? teams.filter(t => t.toLowerCase().includes(filter)) : teams;

    grid.innerHTML = visible.map(t => {
        const selected = teamForm.selected.has(t);
        return `<button onclick="window.toggleTeamSelect('${escapeJs(t)}')"
            class="team-chip ${selected ? 'selected' : ''}">
            ${t}
        </button>`;
    }).join('') || `<span style="font-size:var(--type-xs);color:var(--text-3);font-style:italic;padding:var(--sp-2);">Keine Treffer</span>`;

    // One-time wire-up for the search input.
    const searchEl = document.getElementById('team-compare-search');
    if (searchEl && !searchEl._wired) {
        searchEl.addEventListener('input', e => {
            teamForm.search = e.target.value;
            renderTeamSelector();
        });
        searchEl._wired = true;
    }
}

function renderCompareChart() {
    if (charts.elo) charts.elo.destroy();
    const teams = [...teamForm.selected];
    if (teams.length === 0) {
        const ctx = document.getElementById('eloChart')?.getContext('2d');
        if (ctx) ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
        return;
    }

    // Build the shared X-axis: union of all timestamps across selected teams.
    const allEntries = [];
    teams.forEach(t => (teamForm.history[t] || []).forEach(e => allEntries.push({ team: t, ...e })));
    const sortedTimes = [...new Set(allEntries.map(e => e.timestamp))].sort((a, b) => a - b);

    const labels = sortedTimes.map(ts => {
        if (ts === 0) return 'Start';
        return new Date(ts * 1000).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
    });

    const datasets = teams.map((t, i) => {
        const color = COMPARE_COLORS[i % COMPARE_COLORS.length];
        const teamHist = teamForm.history[t] || [];

        // Carry-forward: if a team didn't play on a given timestamp, show its last known Elo.
        const data = sortedTimes.map(ts => {
            const exact = teamHist.find(e => e.timestamp === ts);
            if (exact) return exact.elo;
            const prev = teamHist.filter(e => e.timestamp <= ts).sort((a, b) => b.timestamp - a.timestamp)[0];
            return prev ? prev.elo : null;
        });

        return {
            label: t,
            data,
            borderColor: color, backgroundColor: color + '15',
            borderWidth: 2.5, pointRadius: 4, pointHoverRadius: 7,
            pointBackgroundColor: color, tension: 0.3, fill: false,
            // Carried alongside the dataset so the tooltip can show "✅ 3:1 vs Senegal"
            opponentInfo: sortedTimes.map(ts => {
                const entry = teamHist.find(e => e.timestamp === ts);
                if (!entry || entry.match_id === 'baseline') return null;
                return teamForm.matchInfo[t]?.[entry.match_id] || null;
            }),
        };
    });

    const tick = (getComputedStyle(document.documentElement).getPropertyValue('--text-3') || '#888').trim();
    const text1 = (getComputedStyle(document.documentElement).getPropertyValue('--text-1') || '#fff').trim();

    charts.elo = new Chart(document.getElementById('eloChart'), {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { labels: { color: text1, boxWidth: 16, font: { size: 12 } } },
                tooltip: {
                    backgroundColor: 'rgba(20,12,8,0.95)', titleColor: '#f3d56e',
                    bodyColor: text1, borderColor: 'rgba(212,175,55,0.4)', borderWidth: 1,
                    padding: 12, displayColors: true,
                    callbacks: {
                        label: ctx => {
                            const info = ctx.dataset.opponentInfo?.[ctx.dataIndex];
                            const elo = ctx.parsed.y?.toFixed(0);
                            if (info) {
                                const emoji = info.result === 'W' ? 'W' : info.result === 'L' ? 'L' : 'D';
                                return `${ctx.dataset.label}: ${elo}  ${emoji} ${info.score} vs ${info.opponent}`;
                            }
                            return `${ctx.dataset.label}: ${elo}`;
                        },
                    },
                },
            },
            scales: {
                x: { ticks: { color: tick, font: { size: 10 } }, grid: { display: false } },
                y: { ticks: { color: tick, font: { size: 11 } }, grid: { color: 'rgba(255,255,255,0.05)' },
                     title: { display: true, text: 'Elo Rating', color: tick } },
            },
        },
    });
}

// Escape a team name for embedding inside a JS string literal in HTML.
function escapeJs(s) { return s.replace(/\\/g, '\\\\').replace(/'/g, "\\'"); }
