// Top Value Bets — fixture list sorted by Expected Points (xP), descending.

import { buildFixtureRow } from './dashboard.js';

export function renderValueBets(matches, openMatch) {
    const grid = document.getElementById('value-bets-grid');
    grid.innerHTML = '';

    const sorted = [...matches]
        .filter(m => m.max_xp > 0)
        .sort((a, b) => b.max_xp - a.max_xp);

    const list = document.createElement('div');
    list.className = 'fixture-group-list';
    sorted.forEach(match => {
        const row = buildFixtureRow(match, /* showXp */ true);
        row.addEventListener('click', () => openMatch(match.id));
        list.appendChild(row);
    });
    grid.appendChild(list);
}
