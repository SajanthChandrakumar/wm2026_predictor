// Single source of truth for all /api/* network calls.
// Throws on non-2xx — callers decide how to surface the error.

async function getJson(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${url} → ${res.status}`);
    return res.json();
}

async function postJson(url, body) {
    const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `${url} → ${res.status}`);
    return data;
}

export const api = {
    quota:        ()       => getJson('/api/quota'),
    matches:      (force)  => getJson(force ? '/api/matches?force=true' : '/api/matches'),
    archive:      ()       => getJson('/api/archive'),
    eloHistory:   ()       => getJson('/api/elo_history'),
    eloRatings:   ()       => getJson('/api/elo_ratings'),

    predict:      (payload)             => postJson('/api/predict', payload),
    syncElo:      ()                    => getJson('/api/sync_elo'),
    saveUserTip:  (match_id, user_tip)  => postJson('/api/archive/user_tip', { match_id, user_tip }),

    customBot:        ()        => getJson('/api/custom_bot'),
    simulateCustomBot:(params)  => postJson('/api/custom_bot/simulate', { params }),
    saveCustomBot:    (cfg)     => postJson('/api/custom_bot', cfg),
};
