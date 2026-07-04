// Pure helpers — no DOM, no state.

// Format implied probabilities (rounded percent). Non-finite / zero → dash,
// so placeholder KO fixtures (teams TBD, no odds) don't render "NaN%".
export const pct = p => (Number.isFinite(p) && p > 0) ? (p * 100).toFixed(0) + '%' : '–';

// Remove the bookmaker margin from h2h decimal odds → true probabilities.
// Returns zeros when odds are missing (e.g. undecided bracket slots) so the
// probability bars collapse to empty instead of producing NaN widths.
export function computeImpliedProbs(odds) {
    if (!odds || !odds.home || !odds.draw || !odds.away) {
        return { home: 0, draw: 0, away: 0 };
    }
    const rh = 1 / odds.home, rd = 1 / odds.draw, ra = 1 / odds.away;
    const t = rh + rd + ra;
    return { home: rh / t, draw: rd / t, away: ra / t };
}

// Heatmap cell color — interpolates through a 3-stop gradient, theme-aware.
export function probColor(prob, maxProb) {
    const isLight = document.body.getAttribute('data-theme') === 'light';
    if (!prob || !maxProb) return isLight ? '#f5f0e6' : '#0d1220';
    const r = Math.min(prob / maxProb, 1);

    const darkStops  = [[13,18,32], [90,55,10], [210,148,26]];
    const lightStops = [[245,240,230], [217,140,88], [200,121,65]];
    const stops = isLight ? lightStops : darkStops;

    let c1, c2, t;
    if (r < 0.5) { c1 = stops[0]; c2 = stops[1]; t = r / 0.5; }
    else         { c1 = stops[1]; c2 = stops[2]; t = (r - 0.5) / 0.5; }
    const mix = i => Math.round(c1[i] + (c2[i] - c1[i]) * t);
    return `rgb(${mix(0)},${mix(1)},${mix(2)})`;
}

// Map archive (Odds-API) team names → normalized Elo team names.
// Used by Team Form view to join archive entries with elo_history.
const TEAM_NORMALIZE = {
    "United States": "United States", "USA": "United States",
    "Korea Republic": "South Korea", "South Korea": "South Korea",
    "Czechia": "Czech Republic", "Czech Republic": "Czech Republic",
    "IR Iran": "Iran", "Côte d'Ivoire": "Ivory Coast", "Ivory Coast": "Ivory Coast",
    "Türkiye": "Türkiye", "Turkey": "Türkiye",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Bosnia and Herzegovina": "Bosnia and Herzegovina",
};
export const normTeam = t => TEAM_NORMALIZE[t] || t;

// Country flag emoji lookup.
const FLAGS = {
    "Argentina":"🇦🇷","Brazil":"🇧🇷","France":"🇫🇷","Germany":"🇩🇪","Spain":"🇪🇸","England":"🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Netherlands":"🇳🇱","Portugal":"🇵🇹","Italy":"🇮🇹","Belgium":"🇧🇪","Croatia":"🇭🇷","Switzerland":"🇨🇭",
    "Denmark":"🇩🇰","Sweden":"🇸🇪","Austria":"🇦🇹","Czech Republic":"🇨🇿","Türkiye":"🇹🇷","Norway":"🇳🇴",
    "Poland":"🇵🇱","Mexico":"🇲🇽","United States":"🇺🇸","Canada":"🇨🇦","Uruguay":"🇺🇾","Colombia":"🇨🇴",
    "Ecuador":"🇪🇨","Paraguay":"🇵🇾","South Korea":"🇰🇷","Japan":"🇯🇵","Iran":"🇮🇷","Saudi Arabia":"🇸🇦",
    "Iraq":"🇮🇶","Australia":"🇦🇺","New Zealand":"🇳🇿","Morocco":"🇲🇦","Senegal":"🇸🇳","Ivory Coast":"🇨🇮",
    "Tunisia":"🇹🇳","Algeria":"🇩🇿","Egypt":"🇪🇬","Ghana":"🇬🇭","Cameroon":"🇨🇲","Nigeria":"🇳🇬",
    "DR Congo":"🇨🇩","South Africa":"🇿🇦","Qatar":"🇶🇦","Jordan":"🇯🇴","Curaçao":"🇨🇼","Cape Verde":"🇨🇻",
    "Scotland":"🏴󠁧󠁢󠁳󠁣󠁴󠁿","Wales":"🏴󠁧󠁢󠁷󠁬󠁳󠁿","Haiti":"🇭🇹","Uzbekistan":"🇺🇿","Bosnia and Herzegovina":"🇧🇦",
};
export const flag = t => FLAGS[t] || '🏳️';
