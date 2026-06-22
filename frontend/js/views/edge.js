// Model Edge — where Elo disagrees most with the bookmaker market.

export function renderEdgeView(matches, openMatch) {
    const grid = document.getElementById('edge-grid');
    grid.innerHTML = '';
    const now = new Date();

    const rows = matches
        .filter(m => m.edge_home != null && new Date(m.raw_match.commence_time) > now)
        .sort((a, b) => Math.abs(b.edge_home) - Math.abs(a.edge_home));

    if (!rows.length) {
        grid.innerHTML = `<p style="color:var(--text-2);font-size:var(--type-body);">Keine Edge-Daten verfügbar — Daten aktualisieren.</p>`;
        return;
    }

    rows.forEach(m => {
        const edgePts = m.edge_home * 100;
        const absEdge = Math.abs(edgePts);
        const favTeam = edgePts >= 0 ? m.home_disp : m.away_disp;
        const strengthVar = absEdge >= 12 ? 'var(--green-l)' : absEdge >= 6 ? 'var(--amber-l)' : 'var(--text-3)';

        const mShare = m.market_home_share * 100;
        const eShare = m.elo_home_share * 100;

        const when = new Date(m.raw_match.commence_time).toLocaleDateString('de-CH', {
            weekday: 'short', day: '2-digit', month: '2-digit', timeZone: 'Europe/Zurich',
        });

        const card = document.createElement('div');
        card.className = 'glass-card edge-card';
        card.style.borderLeftColor = strengthVar;
        card.addEventListener('click', () => openMatch(m.id));
        card.innerHTML = `
            <div class="edge-card-header">
                <div class="edge-value" style="color:${strengthVar}">
                    ${edgePts >= 0 ? '+' : ''}${edgePts.toFixed(1)}<span class="edge-unit">pp</span>
                </div>
                <div class="edge-match-info">
                    <div class="edge-match-title">
                        ${m.home_disp} <span style="color:var(--text-3);font-weight:500;">vs</span> ${m.away_disp}
                    </div>
                    <div class="edge-match-meta">
                        ${when} · Elo favorisiert <strong style="color:var(--text-1);">${favTeam}</strong>
                    </div>
                </div>
            </div>
            <div class="edge-bars">
                ${edgeBar('Markt', mShare, 'var(--blue-l)')}
                ${edgeBar('Elo',   eShare, 'var(--gold)')}
            </div>
        `;
        grid.appendChild(card);
    });
}

function edgeBar(label, homePct, color) {
    return `
        <div class="edge-bar-row">
            <span class="edge-bar-label">${label}</span>
            <span class="edge-bar-pct">${homePct.toFixed(0)}%</span>
            <div class="edge-bar-track">
                <div class="edge-bar-fill" style="width:${homePct}%;background:${color};"></div>
            </div>
            <span class="edge-bar-pct" style="text-align:left;">${(100 - homePct).toFixed(0)}%</span>
        </div>
    `;
}
