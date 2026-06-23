import { api } from '../api.js?v=2';

// 48 teams allocated into 12 groups.
// The tables will automatically compute standings from the match results.
const WC_GROUPS = {
    A: ['Mexico', 'South Africa', 'South Korea', 'Czechia'],
    B: ['Canada', 'Bosnia and Herzegovina', 'Qatar', 'Switzerland'],
    C: ['Brazil', 'Morocco', 'Haiti', 'Scotland'],
    D: ['USA', 'Paraguay', 'Australia', 'Türkiye'],
    E: ['Germany', 'Curaçao', 'Ivory Coast', 'Ecuador'],
    F: ['Netherlands', 'Japan', 'Sweden', 'Tunisia'],
    G: ['Belgium', 'Egypt', 'Iran', 'New Zealand'],
    H: ['Spain', 'Cape Verde', 'Saudi Arabia', 'Uruguay'],
    I: ['France', 'Senegal', 'Iraq', 'Norway'],
    J: ['Argentina', 'Algeria', 'Austria', 'Jordan'],
    K: ['Portugal', 'DR Congo', 'Uzbekistan', 'Colombia'],
    L: ['England', 'Croatia', 'Ghana', 'Panama'],
};

const TEAM_NORMALIZE = {
    "United States": "USA", "USA": "USA",
    "Korea Republic": "South Korea", "South Korea": "South Korea",
    "IR Iran": "Iran", "Côte d'Ivoire": "Ivory Coast", "Ivory Coast": "Ivory Coast",
    "Turkey": "Türkiye", "Türkiye": "Türkiye",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Czech Republic": "Czechia", "Czechia": "Czechia",
    "Curacao": "Curaçao"
};
const norm = t => TEAM_NORMALIZE[t] || t;

export async function loadGroupsView() {
    const grid = document.getElementById('groups-grid');
    grid.innerHTML = '<p style="color:var(--text-3);font-size:var(--type-sm);">Computing Live Standings…</p>';

    let archive;
    try {
        archive = await api.archive();
    } catch (e) {
        grid.innerHTML = `<p style="color:var(--red-l);">Failed to load results: ${e.message}</p>`;
        return;
    }

    // 1. Extract completed matches
    const completed = [];
    Object.entries(archive).forEach(([, m]) => {
        const pmr = m.post_match_result;
        if (pmr?.status !== 'completed' || !pmr.actual_score) return;
        
        // Skip knockout matches for group standings
        if (m.metadata?.is_ko_phase) return;

        const [hs, as] = pmr.actual_score.split(':').map(Number);
        if (Number.isNaN(hs) || Number.isNaN(as)) return;
        completed.push({ 
            home: norm(m.metadata.home_team), 
            away: norm(m.metadata.away_team), 
            hs, 
            as 
        });
    });

    grid.innerHTML = '';
    const container = document.createElement('div');
    container.className = 'groups-container';

    // 2. Compute standings per group dynamically
    Object.entries(WC_GROUPS).forEach(([letter, teams]) => {
        const standings = teams.map(t => ({ team: t, p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 }));
        const teamMap = Object.fromEntries(standings.map(s => [norm(s.team), s]));

        completed.forEach(m => {
            const h = teamMap[m.home];
            const a = teamMap[m.away];
            if (!h || !a) return; // Cross-group matches or friendlies are ignored

            h.p++; a.p++;
            h.gf += m.hs; h.ga += m.as;
            a.gf += m.as; a.ga += m.hs;

            if (m.hs > m.as) { h.w++; h.pts += 3; a.l++; }
            else if (m.hs < m.as) { a.w++; a.pts += 3; h.l++; }
            else { h.d++; a.d++; h.pts += 1; a.pts += 1; }
        });

        // 3. Sort by Points > Goal Difference > Goals For
        standings.sort((a, b) => b.pts - a.pts || (b.gf - b.ga) - (a.gf - a.ga) || b.gf - a.gf);

        const rowsHtml = standings.map((s, i) => {
            const gd = s.gf - s.ga;
            const gdStr = gd > 0 ? `+${gd}` : `${gd}`;
            const qualClass = i < 2 ? 'group-qualify' : i === 2 ? 'group-playoff' : '';
            return `<tr class="${qualClass}">
                <td class="gr-pos">${i + 1}</td>
                <td class="gr-team">${s.team}</td>
                <td class="gr-num">${s.p}</td>
                <td class="gr-num">${s.w}</td>
                <td class="gr-num">${s.d}</td>
                <td class="gr-num">${s.l}</td>
                <td class="gr-num">${s.gf}:${s.ga}</td>
                <td class="gr-num">${gdStr}</td>
                <td class="gr-pts">${s.pts}</td>
            </tr>`;
        }).join('');

        const card = document.createElement('div');
        card.className = 'group-card';
        card.innerHTML = `
            <div class="group-card-header">Group ${letter}</div>
            <table class="group-table">
                <thead>
                    <tr>
                        <th class="gr-pos">#</th>
                        <th class="gr-team">Team</th>
                        <th class="gr-num" title="Played">P</th>
                        <th class="gr-num" title="Won">W</th>
                        <th class="gr-num" title="Drawn">D</th>
                        <th class="gr-num" title="Lost">L</th>
                        <th class="gr-num" title="Goals">G</th>
                        <th class="gr-num" title="Goal Difference">GD</th>
                        <th class="gr-pts" title="Points">Pts</th>
                    </tr>
                </thead>
                <tbody>${rowsHtml}</tbody>
            </table>`;
        container.appendChild(card);
    });

    grid.appendChild(container);

    // Restore headers
    const header = document.querySelector('#groups-view h1');
    if (header) header.textContent = 'Group Standings';
    const subtitle = document.querySelector('#groups-view .page-subtitle');
    if (subtitle) subtitle.textContent = 'Standings automatically calculated from match results';
}