import json, os, time
from datetime import datetime, timezone
from src.core import config
def extract_odds(match):
    """
    Konsens-Quoten: Median über alle Buchmacher statt erstbester Quote.
    Der Markt-Median ist robuster gegen Ausreisser einzelner Anbieter.
    """
    home_team = match.get('home_team')
    away_team = match.get('away_team')
    collected = {'home': [], 'draw': [], 'away': [], 'over25': [], 'under25': []}
    for bookie in match.get('bookmakers', []):
        for market in bookie.get('markets', []):
            if market['key'] == 'h2h':
                for outcome in market.get('outcomes', []):
                    if outcome['name'] == home_team:
                        collected['home'].append(outcome['price'])
                    elif outcome['name'] == away_team:
                        collected['away'].append(outcome['price'])
                    elif outcome['name'] == 'Draw':
                        collected['draw'].append(outcome['price'])
            elif market['key'] == 'totals':
                for outcome in market.get('outcomes', []):
                    if outcome.get('point') == 2.5:
                        if outcome['name'] == 'Over':
                            collected['over25'].append(outcome['price'])
                        elif outcome['name'] == 'Under':
                            collected['under25'].append(outcome['price'])
    odds = {k: statistics.median(v) for k, v in collected.items() if v}
    required_keys = ['home', 'draw', 'away']
    missing_keys = [k for k in required_keys if k not in odds]
    if missing_keys:
        raise ValueError('Keine Quoten für diesen Markt verfügbar')
    return odds

def _dynamic_ttl(matches: list) -> int:
    """Return cache TTL in seconds based on soonest upcoming kickoff."""
    now = time.time()
    soonest = None
    for m in matches:
        ct = m.get('raw_match', m).get('commence_time', '')
        if ct:
            try:
                dt = datetime.fromisoformat(ct.replace('Z', '+00:00'))
                diff = dt.timestamp() - now
                if diff > 0 and (soonest is None or diff < soonest):
                    soonest = diff
            except Exception:
                pass
    if soonest is None:
        return 3600
    if soonest > 86400:
        return 43200
    if soonest > 7200:
        return 3600
    return 900

def _fetch_or_cache_totals(event_id: str, raw_match: dict) -> dict:
    """
    Return raw_match augmented with totals bookmakers, fetching from the
    single-event endpoint (1 request) only if the per-match cache is stale.
    """
    totals_cache = {}
    if os.path.exists(totals_cache_path):
        try:
            with open(totals_cache_path, 'r', encoding='utf-8') as f:
                totals_cache = json.load(f)
        except Exception:
            pass
    entry = totals_cache.get(event_id, {})
    if entry and time.time() - entry.get('timestamp', 0) < TOTALS_CACHE_TTL:
        totals_bookmakers = entry.get('bookmakers', [])
    else:
        try:
            engine = OddsApiEngine()
            event_data = engine.get_event_odds(event_id, market='totals')
            totals_bookmakers = event_data.get('bookmakers', [])
            totals_cache[event_id] = {'timestamp': time.time(), 'bookmakers': totals_bookmakers}
            os.makedirs(os.path.dirname(totals_cache_path), exist_ok=True)
            with open(totals_cache_path, 'w', encoding='utf-8') as f:
                json.dump(totals_cache, f, indent=4)
        except Exception as e:
            print(f'Totals fetch failed for {event_id}: {e}')
            totals_bookmakers = []
    if not totals_bookmakers:
        return raw_match
    existing = {b['key']: b for b in raw_match.get('bookmakers', [])}
    for tb in totals_bookmakers:
        key = tb.get('key')
        if key in existing:
            have_keys = {m['key'] for m in existing[key].get('markets', [])}
            for mkt in tb.get('markets', []):
                if mkt['key'] not in have_keys:
                    existing[key]['markets'].append(mkt)
        else:
            existing[key] = tb
    merged = dict(raw_match)
    merged['bookmakers'] = list(existing.values())
    return merged

def _enrich_edge(matches: list) -> list:
    """
    Berechnet die Edge (Elo vs Markt im Sieg/Niederlage-Pool) aus den bereits
    vorhandenen Quoten — kostet KEINEN API-Request. Idempotent: nur fehlende
    Werte werden ergänzt.
    """
    for m in matches:
        home_norm = TEAM_MAPPING.get(m.get('home_team'), m.get('home_team'))
        away_norm = TEAM_MAPPING.get(m.get('away_team'), m.get('away_team'))
        m['home_form'] = math_engine.team_forms.get(home_norm, {'form': [], 'on_fire': False})
        m['away_form'] = math_engine.team_forms.get(away_norm, {'form': [], 'on_fire': False})
        if hasattr(global_odds_engine, 'get_h2h'):
            home_id = m.get('home_team_id')
            away_id = m.get('away_team_id')
            if home_id and away_id:
                m['h2h'] = global_odds_engine.get_h2h(home_id, away_id)
            fixture_id = m.get('id')
            commence = m.get('commence_time') or m.get('raw_match', {}).get('commence_time')
            if fixture_id and commence:
                m['lineup_diff'] = global_odds_engine.get_lineup(fixture_id, commence)
        if m.get('edge_home') is not None:
            continue
        odds = m.get('odds', {})
        if not all((k in odds for k in ('home', 'draw', 'away'))):
            continue
        try:
            true_probs = MathEngine.remove_margin(odds['home'], odds['draw'], odds['away'])
            pool = true_probs['home'] + true_probs['away']
            market_home_share = true_probs['home'] / pool if pool > 0 else 0.5
            elo_home_share, _ = math_engine.get_match_elo_probabilities(m.get('home_team'), m.get('away_team'))
            m['elo_home_share'] = elo_home_share
            m['market_home_share'] = market_home_share
            m['edge_home'] = elo_home_share - market_home_share
        except Exception:
            pass
    return matches

