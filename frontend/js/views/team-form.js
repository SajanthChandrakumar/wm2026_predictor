// Team Form view — Power Rankings (sortable table of all teams) +
// Multi-team Elo comparison chart with archive-derived opponent labels.

import { teamForm, charts } from '../state.js';
import { api } from '../api.js';
import { flag, normTeam } from '../util.js';

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
            `<p style="color:var(--red);font-size:0.85rem;">Fehler: ${e.message}</p>`);
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
        const dColor = r.delta > 0 ? 'var(--green)' : r.delta < 0 ? 'var(--red)' : 'var(--text-3)';
        const dSign  = r.delta > 0 ? '▲' : r.delta < 0 ? '▼' : '·';
        const formHtml = r.form.length
            ? r.form.map(x => {
                const c = x === 'W' ? 'var(--green)' : x === 'D' ? 'var(--amber)' : 'var(--red)';
                return `<span style="display:inline-block;width:16px;height:16px;border-radius:3px;background:${c};color:#fff;font-size:0.55rem;font-weight:800;text-align:center;line-height:16px;">${x}</span>`;
            }).join(' ')
            : `<span style="font-size:0.68rem;color:var(--text-3);font-style:italic;">noch nicht gespielt</span>`;
        const isSelected = teamForm.selected.has(r.team);
        const rankColor = i === 0 ? '#ffd166' : i === 1 ? '#d9d9d9' : i === 2 ? '#cd7f32' : 'var(--text-3)';
        const bg = isSelected ? 'var(--gold-dim)' : 'transparent';

        return `<tr data-team="${r.team}"
                    style="border-top:1px solid var(--border);cursor:pointer;background:${bg};transition:background 0.15s;"
                    onclick="window.toggleTeamSelect('${escapeJs(r.team)}')"
                    onmouseover="this.style.background='var(--surface-2)'"
                    onmouseout="this.style.background='${bg}'">
            <td style="padding:8px 14px;font-size:0.78rem;font-weight:800;color:${rankColor};text-align:center;">${i + 1}</td>
            <td style="padding:8px 6px;font-size:0.88rem;font-weight:700;color:var(--text-1);white-space:nowrap;">
                <span style="margin-right:6px;">${flag(r.team)}</span>${r.team}
            </td>
            <td style="padding:8px 12px;text-align:right;font-size:0.85rem;font-weight:800;color:var(--text-1);font-variant-numeric:tabular-nums;">${r.elo.toFixed(0)}</td>
            <td style="padding:8px 12px;text-align:right;font-size:0.78rem;font-weight:700;color:${dColor};font-variant-numeric:tabular-nums;">${dSign} ${Math.abs(r.delta).toFixed(0)}</td>
            <td style="padding:8px 12px;text-align:center;font-size:0.74rem;color:var(--text-2);font-variant-numeric:tabular-nums;">
                <span style="color:var(--green);">${r.w}</span>-<span style="color:var(--amber);">${r.d}</span>-<span style="color:var(--red);">${r.l}</span>
            </td>
            <td style="padding:8px 12px;font-size:0.7rem;">${formHtml}</td>
        </tr>`;
    }).join('');

    panel.innerHTML = `
        <div class="glass-card" style="padding:20px 24px;">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;gap:12px;">
                <div>
                    <div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--text-3);font-weight:700;margin-bottom:3px;">🏆 Power Rankings</div>
                    <div style="font-size:0.72rem;color:var(--text-3);">Sortiert nach aktuellem Elo · Klick = im Chart vergleichen</div>
                </div>
                <div style="font-size:0.7rem;color:var(--text-3);">${rows.length} Teams</div>
            </div>
            <div style="max-height:520px;overflow-y:auto;border-radius:4px;">
                <table style="width:100%;border-collapse:collapse;">
                    <thead style="position:sticky;top:0;background:var(--surface);z-index:1;">
                        <tr>${['#', 'Team', 'Elo', 'Δ Start', 'W-D-L', 'Form'].map((h, i) =>
                            `<th style="padding:8px ${i === 1 ? '6' : '12'}px;text-align:${[0, 4].includes(i) ? 'center' : [2, 3].includes(i) ? 'right' : 'left'};font-size:0.62rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-3);font-weight:700;">${h}</th>`
                        ).join('')}</tr>
                    </thead>
                    <tbody>${rowsHtml}</tbody>
                </table>
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
        const fg = selected ? 'var(--gold-l)' : 'var(--text-2)';
        const bg = selected ? 'var(--gold-dim)' : 'var(--surface-2)';
        const bd = selected ? 'var(--gold-b)' : 'var(--border-2)';
        return `<button onclick="window.toggleTeamSelect('${escapeJs(t)}')"
            style="background:${bg};border:1px solid ${bd};color:${fg};padding:5px 10px;border-radius:4px;font-size:0.72rem;font-weight:600;cursor:pointer;white-space:nowrap;transition:all 0.15s;">
            ${flag(t)} ${t}
        </button>`;
    }).join('') || `<span style="font-size:0.72rem;color:var(--text-3);font-style:italic;padding:8px;">Keine Treffer</span>`;

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
            label: `${flag(t)} ${t}`,
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
                                const emoji = info.result === 'W' ? '✅' : info.result === 'L' ? '❌' : '🟰';
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
