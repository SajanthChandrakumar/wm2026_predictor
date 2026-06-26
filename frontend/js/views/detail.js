// Match detail view: xG row, score-probability heatmap, odds, tip ladder.

import { state } from '../state.js';
import { api } from '../api.js?v=3';
import { pct, computeImpliedProbs, probColor } from '../util.js';
import { renderFormBlocks } from './dashboard.js';

export function renderDetail(matchInfo, calc) {
    const isKo = document.getElementById('ko-toggle').checked;

    // Title & meta chips
    document.getElementById('match-title').textContent =
        `${matchInfo.home_disp} vs ${matchInfo.away_disp}`;

    const metaChips = [
        isKo ? '<span class="meta-chip ko">K.O. Phase</span>' : '<span class="meta-chip">Group Stage</span>',
        `<span class="meta-chip">xG ${calc.xg_home.toFixed(2)} – ${calc.xg_away.toFixed(2)}</span>`,
    ];
    if (matchInfo.h2h && matchInfo.home_team_id && matchInfo.away_team_id) {
        const h2h = matchInfo.h2h;
        const w1 = h2h[matchInfo.home_team_id] || 0;
        const w2 = h2h[matchInfo.away_team_id] || 0;
        const d  = h2h.draws || 0;
        if (w1 || w2 || d) metaChips.push(`<span class="meta-chip">H2H ${w1}W – ${d}D – ${w2}L</span>`);
    }
    document.getElementById('match-meta').innerHTML = metaChips.join('');

    // xG row + lineup alert (if API-Football engine returned diffs)
    const homeFire = matchInfo.home_form?.on_fire ? '<span class="fire-badge" title="In top form"></span>' : '';
    const awayFire = matchInfo.away_form?.on_fire ? '<span class="fire-badge" title="In top form"></span>' : '';

    const diffs = matchInfo.lineup_diff || {};
    const homeDiff = diffs[matchInfo.home_team]?.missing || [];
    const awayDiff = diffs[matchInfo.away_team]?.missing || [];
    let lineupAlertHtml = '';
    if (homeDiff.length || awayDiff.length) {
        const msg = [];
        if (homeDiff.length) msg.push(`<strong>${matchInfo.home_disp}</strong> missing: ${homeDiff.join(', ')}`);
        if (awayDiff.length) msg.push(`<strong>${matchInfo.away_disp}</strong> missing: ${awayDiff.join(', ')}`);
        lineupAlertHtml = `<div class="lineup-alert">⚠️ <strong>Lineup Alert:</strong> ${msg.join(' | ')}</div>`;
    }

    document.getElementById('xg-row').innerHTML = `
        ${lineupAlertHtml}
        <div class="xg-team home">
            <span class="xg-team-name">${matchInfo.home_disp}${homeFire}</span>
            ${renderFormBlocks(matchInfo.home_form?.form)}
            <span class="xg-value">${calc.xg_home.toFixed(2)}</span>
            <span class="xg-label">Expected Goals</span>
        </div>
        <div class="xg-divider">
            <span>vs</span>
            <small>xG</small>
        </div>
        <div class="xg-team away">
            <span class="xg-team-name">${matchInfo.away_disp}${awayFire}</span>
            ${renderFormBlocks(matchInfo.away_form?.form)}
            <span class="xg-value">${calc.xg_away.toFixed(2)}</span>
            <span class="xg-label">Expected Goals</span>
        </div>
    `;

    renderHeatmap(matchInfo, calc);

    // Odds card with inline probability bars
    const probs = computeImpliedProbs(matchInfo.odds);
    document.getElementById('odds-card').innerHTML = `
        <div class="card-title">Bookmaker Odds</div>
        ${oddsRow(matchInfo.home_disp, probs.home, matchInfo.odds.home)}
        ${oddsRow('Draw', probs.draw, matchInfo.odds.draw)}
        ${oddsRow(matchInfo.away_disp, probs.away, matchInfo.odds.away)}
    `;

    renderTipLadder(calc.xp_tips);
    renderBotTips(matchInfo.bots);
    document.getElementById('adopt-tip-status').textContent = '';
    updateAdoptButton();
}

function oddsRow(label, prob, price) {
    const barWidth = (prob * 100).toFixed(1);
    const isDrawRow = label === 'Draw';
    return `
        <div class="odds-row">
            <span class="odds-team" ${isDrawRow ? 'style="color:var(--text-2)"' : ''}>${label}</span>
            <div class="odds-right">
                <span class="odds-pct">${pct(prob)}</span>
                <div class="odds-bar-wrap">
                    <div class="odds-bar-fill" style="width:${barWidth}%"></div>
                </div>
                <span class="odds-price">${price.toFixed(2)}</span>
            </div>
        </div>
    `;
}

function currentActiveTip() {
    return state.lastCalcData?.xp_tips?.[0]?.Tipp ?? null;
}

function updateAdoptButton() {
    const btn = document.getElementById('adopt-tip-btn');
    if (!btn) return;
    const tip = currentActiveTip();
    btn.textContent = tip ? `Tipp übernehmen: ${tip}` : 'Tipp übernehmen';
    btn.disabled = !tip;
    btn.onclick = () => adoptCurrentTip();
}

async function adoptCurrentTip() {
    const tip = currentActiveTip();
    if (!tip || !state.selectedMatchId) return;
    const btn = document.getElementById('adopt-tip-btn');
    const status = document.getElementById('adopt-tip-status');
    btn.disabled = true;
    const prev = btn.textContent;
    btn.textContent = 'Speichere…';
    try {
        await api.saveUserTip(state.selectedMatchId, tip);
        status.style.color = 'var(--green-l)';
        status.textContent = `✓ ${tip} als dein Tipp gespeichert`;
    } catch (e) {
        status.style.color = 'var(--red-l)';
        status.textContent = `✗ ${e.message}`;
    }
    btn.textContent = prev;
    btn.disabled = false;
}

function renderTipLadder(tips) {
    const container = document.getElementById('xp-container');
    if (!tips?.length) {
        container.innerHTML = '<p style="color:var(--text-3);font-size:var(--type-sm);">No tips available.</p>';
        return;
    }
    const top = tips[0];
    let html = `
        <div class="tip-top">
            <div>
                <div class="tip-top-label-overline">Top Pick</div>
                <div class="tip-top-score">${top.Tipp}</div>
            </div>
            <div class="tip-top-right">
                <div class="tip-top-xp">${top.xP.toFixed(2)} xP</div>
                <div class="tip-top-label">Expected Points</div>
            </div>
        </div>
    `;
    for (let i = 1; i < Math.min(4, tips.length); i++) {
        const t = tips[i];
        html += `
            <div class="tip-row">
                <span class="tip-rank">#${i + 1}</span>
                <span class="tip-score">${t.Tipp}</span>
                <span class="tip-xp-val">${t.xP.toFixed(2)} xP</span>
            </div>`;
    }
    container.innerHTML = html;
}

const BOT_META = {
    broker:    { label: 'Broker',    color: 'var(--blue)'   },
    professor: { label: 'Professor', color: 'var(--green)'  },
    sniper:    { label: 'X-Sniper',  color: 'var(--purple)' },
    gambler:   { label: 'Zocker',    color: 'var(--text-2)' },
};

function renderBotTips(bots) {
    const card = document.getElementById('bot-tips-card');
    if (!card) return;
    const entries = Object.entries(bots || {}).filter(([, v]) => v?.tip);
    if (!entries.length) {
        card.innerHTML = '';
        return;
    }
    const rows = entries.map(([name, info]) => {
        const meta = BOT_META[name] || { label: name, color: 'var(--text-2)' };
        return `
        <div style="display:flex;align-items:center;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--border);">
            <span style="font-size:0.78rem;color:var(--text-secondary)">${meta.label}</span>
            <span style="font-size:0.9rem;font-weight:700;color:${meta.color};font-variant-numeric:tabular-nums">${info.tip}</span>
        </div>`;
    }).join('');
    card.innerHTML = `
        <div class="card-title" style="margin-bottom:10px;">Bot Tips</div>
        ${rows}
    `;
}

function renderHeatmap(matchInfo, calc) {
    const container = document.getElementById('matrix-container');
    const maxP = calc.max_prob;

    let colHeaders = '<div class="axis-num col"></div>';
    for (let a = 0; a <= 5; a++) colHeaders += `<div class="axis-num col">${a}</div>`;

    let rowsHtml = '';
    for (let h = 0; h <= 5; h++) {
        let rowHtml = `<div class="axis-num">${h}</div>`;
        for (let a = 0; a <= 5; a++) {
            const prob = calc.matrix[h]?.[a] ?? 0;
            const bg = probColor(prob, maxP);
            const textColor = prob / maxP > 0.5 ? 'rgba(0,0,0,0.85)' : 'rgba(255,255,255,0.85)';
            const probPct = (prob * 100).toFixed(1) + '%';
            rowHtml += `
                <div class="heatmap-cell" style="background:${bg};color:${textColor}"
                     title="${matchInfo.home_disp} ${h}:${a} ${matchInfo.away_disp} — ${probPct}">
                    <span class="cell-pct">${probPct}</span>
                </div>`;
        }
        rowsHtml += `<div class="heatmap-row">${rowHtml}</div>`;
    }

    container.innerHTML = `
        <div class="heatmap-wrap">
            <div style="font-size:var(--type-2xs);color:var(--text-3);text-align:center;margin-bottom:var(--sp-1);text-transform:uppercase;letter-spacing:1px;font-weight:700;">${matchInfo.away_disp} Goals →</div>
            <div class="heatmap-body">
                <div style="writing-mode:vertical-rl;transform:rotate(180deg);font-size:var(--type-2xs);color:var(--text-3);text-transform:uppercase;letter-spacing:1px;font-weight:700;padding-right:var(--sp-2);display:flex;align-items:center;justify-content:center;">
                    ${matchInfo.home_disp} Goals
                </div>
                <div>
                    <div class="heatmap-row">${colHeaders}</div>
                    ${rowsHtml}
                </div>
            </div>
        </div>
    `;
}
