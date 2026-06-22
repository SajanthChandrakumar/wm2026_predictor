// Shared mutable app state. Plain module exports — no classes, no setters.
// Other modules import this and read/write directly.

export const state = {
    // Current list of matches (dashboard payload)
    currentMatches: [],
    // ID of the match currently shown in the detail view
    selectedMatchId: null,
    // Last /api/predict response — keeps the "Tipp übernehmen" button accurate
    lastCalcData: null,
};

// Chart.js instances live outside `state` because they are not data —
// they are external objects we need to destroy() before redrawing.
export const charts = {
    elo: null,        // Team Form compare chart
    botRace: null,    // Performance: bot-points-race chart
};

// Team Form view internal state (Power Rankings + multi-team compare)
export const teamForm = {
    history: null,    // merged elo_history + ratings, keyed by team
    matchInfo: null,  // per-team match log derived from archive
    selected: new Set(),
    search: '',
};
