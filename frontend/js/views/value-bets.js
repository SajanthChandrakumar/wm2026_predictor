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
    sorted.forEach((match, i) => {
        const row = buildFixtureRow(match, /* showXp */ true);

        // Prepend rank badge
        const rank = document.createElement('div');
        rank.className = 'rank-badge';
        if (i === 0) rank.classList.add('gold');
        else if (i === 1) rank.classList.add('silver');
        else if (i === 2) rank.classList.add('bronze');
        rank.textContent = i + 1;
        row.insertBefore(rank, row.firstChild);

        row.addEventListener('click', () => openMatch(match.id));
        list.appendChild(row);
    });
    grid.appendChild(list);
}
