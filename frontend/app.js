let currentMatches = [];
let maxProb = 0;
let selectedMatchId = null;

document.addEventListener('DOMContentLoaded', () => {
    fetchQuota();
    fetchMatches(); 

    document.getElementById('refresh-btn').addEventListener('click', () => {
        document.getElementById('layout-grid').style.display = 'none';
        document.getElementById('matches-view').style.display = 'none';
        document.getElementById('value-bets-view').style.display = 'none';
        document.getElementById('loading-spinner').style.display = 'flex';
        fetchMatches(true); 
    });

    document.getElementById('nav-dashboard').addEventListener('click', (e) => {
        document.querySelectorAll('nav li').forEach(li => li.classList.remove('active'));
        e.target.classList.add('active');
        document.getElementById('layout-grid').style.display = 'none';
        document.getElementById('value-bets-view').style.display = 'none';
        document.getElementById('matches-view').style.display = 'block';
    });

    document.getElementById('nav-value-bets').addEventListener('click', (e) => {
        document.querySelectorAll('nav li').forEach(li => li.classList.remove('active'));
        e.target.classList.add('active');
        document.getElementById('layout-grid').style.display = 'none';
        document.getElementById('matches-view').style.display = 'none';
        document.getElementById('value-bets-view').style.display = 'block';
        renderValueBets(currentMatches);
    });

    document.getElementById('sync-elo-btn').addEventListener('click', async () => {
        const btn = document.getElementById('sync-elo-btn');
        btn.textContent = 'Syncing...';
        btn.disabled = true;
        try {
            const res = await fetch('/api/sync_elo', { method: 'POST' });
            const data = await res.json();
            alert(data.updates ? `Erfolgreich! ${data.updates} neue Spiele verarbeitet.` : 'Keine neuen Spiele.');
        } catch (e) {
            alert('Fehler bei der Synchronisation.');
        }
        btn.textContent = '🔄 Sync Elo (API)';
        btn.disabled = false;
    });

    document.getElementById('ko-toggle').addEventListener('change', () => {
        if (selectedMatchId) updatePrediction();
    });

    document.getElementById('home-resting-toggle').addEventListener('change', () => {
        if (selectedMatchId) updatePrediction();
    });

    document.getElementById('away-resting-toggle').addEventListener('change', () => {
        if (selectedMatchId) updatePrediction();
    });

    document.getElementById('back-btn').addEventListener('click', () => {
        document.getElementById('layout-grid').style.display = 'none';
        document.getElementById('matches-view').style.display = 'block';
        selectedMatchId = null;
    });
});

async function fetchQuota() {
    try {
        const res = await fetch('/api/quota');
        const data = await res.json();
        document.getElementById('quota-value').textContent = data.remaining !== undefined ? data.remaining : 'Unknown';
        document.getElementById('quota-delta').textContent = `-${data.used !== undefined ? data.used : '?'} used`;
    } catch (e) {
        console.error("Failed to fetch quota", e);
    }
}

async function fetchMatches(force = false) {
    try {
        const url = force ? '/api/matches?force=true' : '/api/matches';
        const res = await fetch(url);
        currentMatches = await res.json();
        
        renderMatchGrid(currentMatches);
        
        // Refresh the Value Bets view if it's currently active
        if (document.getElementById('nav-value-bets').classList.contains('active')) {
            document.getElementById('matches-view').style.display = 'none';
            document.getElementById('value-bets-view').style.display = 'block';
            renderValueBets(currentMatches);
        } else {
            document.getElementById('value-bets-view').style.display = 'none';
            document.getElementById('matches-view').style.display = 'block';
        }
        
        document.getElementById('loading-spinner').style.display = 'none';
        fetchQuota(); 
    } catch (e) {
        document.getElementById('loading-spinner').innerHTML = `<p style="color:red">Fehler: ${e.message}</p>`;
    }
}

function renderMatchGrid(matches) {
    const grid = document.getElementById('matches-grid');
    grid.innerHTML = '';
    
    const sortedMatches = [...matches].sort((a, b) => new Date(a.raw_match.commence_time) - new Date(b.raw_match.commence_time));
    
    sortedMatches.forEach(match => {
        const dateObj = new Date(match.raw_match.commence_time);
        const timeString = dateObj.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });

        const card = document.createElement('div');
        card.className = 'match-card fade-in';
        card.style.animationDelay = `${Math.min(sortedMatches.indexOf(match) * 0.05, 0.5)}s`;
        card.innerHTML = `
            <div class="match-time">🕒 ${timeString}</div>
            <div class="teams">
                <span>${match.home_disp}</span>
                <span class="vs">vs</span>
                <span>${match.away_disp}</span>
            </div>
        `;
        
        card.addEventListener('click', () => {
            selectedMatchId = match.id;
            document.getElementById('home-resting-toggle').checked = false;
            document.getElementById('away-resting-toggle').checked = false;
            document.getElementById('matches-view').style.display = 'none';
            document.getElementById('loading-spinner').style.display = 'flex';
            updatePrediction();
        });
        
        grid.appendChild(card);
    });
}

function renderValueBets(matches) {
    const grid = document.getElementById('value-bets-grid');
    grid.innerHTML = '';
    
    // Filter and sort by max_xp descending
    const sortedMatches = matches
        .filter(m => m.max_xp && m.max_xp > 0)
        .sort((a, b) => b.max_xp - a.max_xp);
        
    sortedMatches.forEach(match => {
        const dateObj = new Date(match.raw_match.commence_time);
        const timeString = dateObj.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });

        const card = document.createElement('div');
        card.className = 'match-card value-bet-card fade-in';
        card.style.animationDelay = `${Math.min(sortedMatches.indexOf(match) * 0.05, 0.5)}s`;
        card.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <span style="font-weight: 700; font-size: 1.1rem;">${match.home_disp} <span style="color:var(--text-muted);font-size:0.9rem;margin:0 6px;">vs</span> ${match.away_disp}</span>
                <span class="match-time" style="margin:0;">🕒 ${timeString}</span>
            </div>
            <div class="value-tip">${match.top_tip}</div>
            <div class="value-xp">Expected Return: ${match.max_xp.toFixed(2)} xP</div>
        `;
        
        card.addEventListener('click', () => {
            selectedMatchId = match.id;
            document.getElementById('home-resting-toggle').checked = false;
            document.getElementById('away-resting-toggle').checked = false;
            document.getElementById('value-bets-view').style.display = 'none';
            document.getElementById('loading-spinner').style.display = 'flex';
            updatePrediction();
        });
        
        grid.appendChild(card);
    });
}

async function updatePrediction() {
    if (!selectedMatchId) return;

    const matchData = currentMatches.find(m => m.id === selectedMatchId);
    const isKo = document.getElementById('ko-toggle').checked;
    const homeResting = document.getElementById('home-resting-toggle').checked;
    const awayResting = document.getElementById('away-resting-toggle').checked;

    document.getElementById('layout-grid').style.display = 'none';
    document.getElementById('loading-spinner').style.display = 'flex';

    try {
        const res = await fetch('/api/predict', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                match: matchData.raw_match, 
                is_ko: isKo,
                home_resting: homeResting,
                away_resting: awayResting
            })
        });
        
        if (!res.ok) {
            let errorMsg = "API Error";
            try {
                const errorData = await res.json();
                errorMsg = errorData.detail || errorMsg;
            } catch(e) {}
            throw new Error(errorMsg);
        }
        const data = await res.json();

        renderDashboard(matchData, data);
        document.getElementById('loading-spinner').style.display = 'none';
        document.getElementById('layout-grid').style.display = 'grid';
    } catch (e) {
        document.getElementById('loading-spinner').innerHTML = `<p style="color:red">Berechnungsfehler: ${e.message}</p>`;
    }
}

function renderDashboard(matchInfo, calcData) {
    document.getElementById('home-resting-label').textContent = matchInfo.home_disp + ' rotiert (B-Elf)';
    document.getElementById('away-resting-label').textContent = matchInfo.away_disp + ' rotiert (B-Elf)';
    document.getElementById('match-title').textContent = `${matchInfo.home_disp} vs ${matchInfo.away_disp}`;

    // Render Matrix
    const matrixContainer = document.getElementById('matrix-container');
    let tableHtml = '<table><thead><tr><th></th>';
    
    // Columns (Away Goals)
    for (let i = 0; i <= 5; i++) tableHtml += `<th>${i}</th>`;
    tableHtml += '</tr></thead><tbody>';

    for (let h = 0; h <= 5; h++) {
        tableHtml += `<tr><th>${h}</th>`;
        for (let a = 0; a <= 5; a++) {
            const prob = calcData.matrix[h] && calcData.matrix[h][a] ? calcData.matrix[h][a] : 0;
            const bgColor = getColorForProb(prob, calcData.max_prob);
            const probPercent = (prob * 100).toFixed(1) + '%';
            tableHtml += `<td style="background-color: ${bgColor}">${probPercent}</td>`;
        }
        tableHtml += '</tr>';
    }
    tableHtml += '</tbody></table>';
    matrixContainer.innerHTML = tableHtml;

    // Render Odds
    const oddsHtml = `
        <div class="team-row">
            <span>${matchInfo.home_disp}</span>
            <span class="odds-pill">${matchInfo.odds.home.toFixed(2)}</span>
        </div>
        <div class="team-row">
            <span style="color: #94A3B8; font-size: 14px;">Draw</span>
            <span class="odds-pill" style="color: #94A3B8;">${matchInfo.odds.draw.toFixed(2)}</span>
        </div>
        <div class="team-row" style="margin-bottom: 0;">
            <span>${matchInfo.away_disp}</span>
            <span class="odds-pill">${matchInfo.odds.away.toFixed(2)}</span>
        </div>
    `;
    document.getElementById('odds-card').innerHTML = oddsHtml;

    // Render XP Tips
    const xpContainer = document.getElementById('xp-container');
    let xpHtml = '';
    
    if (calcData.xp_tips && calcData.xp_tips.length > 0) {
        const topTip = calcData.xp_tips[0];
        xpHtml += `
            <div class="success-card">
                <strong>🎯 Top Pick: ${topTip.Tipp}</strong> (${topTip.xP.toFixed(1)} xP)
            </div>
        `;
        
        for (let i = 1; i < Math.min(4, calcData.xp_tips.length); i++) {
            const tip = calcData.xp_tips[i];
            xpHtml += `
                <div class="metric-card">
                    <label>Rank ${i+1} | Score ${tip.Tipp}</label>
                    <div class="value">${tip.xP.toFixed(1)} xP</div>
                </div>
            `;
        }
    }
    xpContainer.innerHTML = xpHtml;
}

// Colormap interpolation (Deep Blue -> Emerald Green -> Yellow)
function getColorForProb(prob, maxProb) {
    if (maxProb === 0 || prob === 0) return 'rgba(255, 255, 255, 0.03)';
    let ratio = prob / maxProb;
    if (ratio > 1) ratio = 1;

    // Colors: #1E293B (0) -> #38BDF8 (0.33) -> #10B981 (0.66) -> #FACC15 (1)
    const colors = [
        {r: 30, g: 41, b: 59},   // base surface
        {r: 56, g: 189, b: 248}, // accent blue
        {r: 16, g: 185, b: 129}, // success emerald
        {r: 250, g: 204, b: 21}  // warning yellow
    ];

    let c1, c2, localRatio;
    if (ratio < 0.33) {
        c1 = colors[0]; c2 = colors[1];
        localRatio = ratio / 0.33;
    } else if (ratio < 0.66) {
        c1 = colors[1]; c2 = colors[2];
        localRatio = (ratio - 0.33) / 0.33;
    } else {
        c1 = colors[2]; c2 = colors[3];
        localRatio = (ratio - 0.66) / 0.34;
    }

    const r = Math.round(c1.r + (c2.r - c1.r) * localRatio);
    const g = Math.round(c1.g + (c2.g - c1.g) * localRatio);
    const b = Math.round(c1.b + (c2.b - c1.b) * localRatio);

    return `rgb(${r}, ${g}, ${b})`;
}
