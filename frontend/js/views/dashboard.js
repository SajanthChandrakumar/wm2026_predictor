// Dashboard view — list of all tournament fixtures grouped by day.
// Also exports `buildFixtureRow` because value-bets and edge views reuse it.

import { state } from '../state.js';
import { pct, computeImpliedProbs } from '../util.js';

// Public entry: render the dashboard grid + wire row clicks → openMatch.
export function renderMatchGrid(matches, openMatch) {
    const grid = document.getElementById('matches-grid');
    grid.innerHTML = '';

    const sorted = [...matches].sort((a, b) =>
        new Date(a.raw_match.commence_time) - new Date(b.raw_match.commence_time));

    // Group by Zurich-local weekday (matches the SRF Tippspiel UI convention)
    const groups = {};
    sorted.forEach(match => {
        const d = new Date(match.raw_match.commence_time);
        const key = d.toLocaleDateString('de-CH', {
            weekday: 'long', day: 'numeric', month: 'long',
            timeZone: 'Europe/Zurich',
        });
        (groups[key] ||= []).push(match);
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

// Reusable: a single fixture row. Used by dashboard + value-bets + edge views.
export function buildFixtureRow(match, showXp = false) {
    const row = document.createElement('div');
    row.className = 'fixture-row';

    const d = new Date(match.raw_match.commence_time);
    const isPast = d < new Date();

    const timeStr = d.toLocaleTimeString('de-CH', {
        hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Zurich',
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

// Compact form-block strip used in detail view xG row.
export function renderFormBlocks(formArray) {
    if (!formArray || formArray.length === 0) return '';
    const blocks = formArray.map(f => {
        const cls = f.result === 'W' ? 'form-w' : f.result === 'D' ? 'form-d' : 'form-l';
        const title = `${f.result} vs ${f.opponent} (${f.score}) ${f.delta > 0 ? '+' : ''}${f.delta} Elo`;
        return `<span class="form-block ${cls}" title="${title}">${f.result}</span>`;
    }).join('');
    return `<div class="form-container">${blocks}</div>`;
}
