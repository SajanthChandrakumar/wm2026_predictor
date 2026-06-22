// Model Edge — where Elo disagrees most with the bookmaker market.

export function renderEdgeView(matches, openMatch) {
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
        const favTeam = edgePts >= 0 ? m.home_disp : m.away_disp;
        const strength = absEdge >= 12 ? 'var(--green)' : absEdge >= 6 ? 'var(--amber)' : 'var(--text-3)';

        const mShare = m.market_home_share * 100;
        const eShare = m.elo_home_share * 100;

        const when = new Date(m.raw_match.commence_time).toLocaleDateString('de-CH', {
            weekday: 'short', day: '2-digit', month: '2-digit', timeZone: 'Europe/Zurich',
        });

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
                ${edgeBar('Markt', mShare, 'var(--blue)')}
                ${edgeBar('Elo',   eShare, 'var(--gold)')}
            </div>
        `;
        grid.appendChild(card);
    });
}

function edgeBar(label, homePct, color) {
    return `
        <div style="display:flex;align-items:center;gap:10px;">
            <span style="font-size:0.6rem;color:var(--text-3);font-weight:700;text-transform:uppercase;min-width:34px;">${label}</span>
            <span style="font-size:0.62rem;color:var(--text-2);min-width:30px;text-align:right;">${homePct.toFixed(0)}%</span>
            <div style="flex:1;height:7px;background:var(--surface-3);border-radius:4px;overflow:hidden;display:flex;">
                <div style="width:${homePct}%;height:100%;background:${color};"></div>
            </div>
            <span style="font-size:0.62rem;color:var(--text-2);min-width:30px;">${(100 - homePct).toFixed(0)}%</span>
        </div>
    `;
}
