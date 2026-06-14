import json, os, traceback
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from src.core import config
from src.services import match_service, elo_service, prediction_service
router = APIRouter()

@router.get('/api/quota')
def get_quota():
    quota_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'api_quota.json')
    try:
        with open(quota_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'remaining': 'Unknown', 'used': 'Unknown', 'limit': 'Unknown'}

@router.get('/api/matches')
def get_matches(force: bool=False):
    """
    Holt die Spiele. Nutzt den Cache, es sei denn, force=True wird übergeben.
    """
    math_engine.reload_elo_data()
    if not force and os.path.exists(cache_file_path):
        try:
            with open(cache_file_path, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
                timestamp = cached_data.get('timestamp', 0)
                data = cached_data.get('data')
                if data is not None:
                    ttl = _dynamic_ttl(data)
                    if time.time() - timestamp < ttl:
                        return _enrich_edge(data)
        except json.JSONDecodeError:
            pass
    engine = OddsApiEngine()
    data = engine.get_world_cup_odds(market='h2h')
    results = []
    _bot_inputs = {}
    for m in data:
        home_raw = m.get('home_team')
        away_raw = m.get('away_team')
        try:
            event_id = m.get('id', '')
            m = _fetch_or_cache_totals(event_id, m)
            odds = extract_odds(m)
            try:
                math_engine.ensure_teams_exist(TEAM_MAPPING.get(home_raw, home_raw), TEAM_MAPPING.get(away_raw, away_raw))
                true_probs = MathEngine.remove_margin(odds['home'], odds['draw'], odds['away'])
                elo_home_share, elo_away_share = math_engine.get_match_elo_probabilities(home_raw, away_raw)
                win_loss_pool = true_probs['home'] + true_probs['away']
                prob_home = (true_probs['home'] / win_loss_pool * 0.7 + elo_home_share * 0.3) * win_loss_pool
                prob_away = (true_probs['away'] / win_loss_pool * 0.7 + elo_away_share * 0.3) * win_loss_pool
                prob_draw = true_probs['draw']
                if 'over25' in odds and 'under25' in odds:
                    raw_over = 1.0 / odds['over25']
                    raw_under = 1.0 / odds['under25']
                    prob_over25 = raw_over / (raw_over + raw_under)
                else:
                    prob_over25 = None
                xg_h, xg_a = math_engine.derive_xg_from_odds(prob_home, prob_draw, prob_away, prob_over25)
                sm = math_engine.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
                df_xp = math_engine.calculate_expected_points(sm, is_ko_phase=False)
                if not df_xp.empty:
                    top_tip = df_xp.iloc[0]['Tipp']
                    max_xp = float(df_xp.iloc[0]['xP'])
                else:
                    top_tip = 'N/A'
                    max_xp = 0.0
                market_home_share = true_probs['home'] / win_loss_pool if win_loss_pool > 0 else 0.5
                edge_home = elo_home_share - market_home_share
                if event_id and top_tip != 'N/A':
                    _bot_inputs[event_id] = {'score_matrix': sm, 'base_xp_df': df_xp, 'true_probs': true_probs, 'prob_over25': prob_over25}
            except Exception:
                top_tip = 'N/A'
                max_xp = 0.0
                elo_home_share = None
                market_home_share = None
                edge_home = None
            results.append({'id': m.get('id'), 'home_team': home_raw, 'away_team': away_raw, 'home_disp': DISPLAY_MAPPING.get(home_raw, home_raw), 'away_disp': DISPLAY_MAPPING.get(away_raw, away_raw), 'odds': odds, 'top_tip': top_tip, 'max_xp': max_xp, 'elo_home_share': elo_home_share, 'market_home_share': market_home_share, 'edge_home': edge_home, 'raw_match': m})
        except ValueError:
            continue
    try:
        os.makedirs(os.path.dirname(cache_file_path), exist_ok=True)
        existing_matches = {}
        if os.path.exists(cache_file_path):
            try:
                with open(cache_file_path, 'r', encoding='utf-8') as f:
                    existing_matches = {m['id']: m for m in json.load(f).get('data', [])}
            except Exception:
                pass
        for r in results:
            prev = existing_matches.get(r['id'])
            if prev:
                old_o, new_o = (prev.get('odds', {}), r.get('odds', {}))
                odds_changed = any((abs(new_o.get(k, 0) - old_o.get(k, 0)) > 0.02 for k in ['home', 'draw', 'away']))
                missing_edge = 'edge_home' not in prev and r.get('edge_home') is not None
                if not odds_changed and (not missing_edge):
                    continue
            existing_matches[r['id']] = r
        merged = sorted(existing_matches.values(), key=lambda m: m.get('raw_match', {}).get('commence_time', ''))
        with open(cache_file_path, 'w', encoding='utf-8') as f:
            json.dump({'timestamp': time.time(), 'data': merged}, f, indent=4)
    except Exception as e:
        print(f'Fehler beim Speichern des Caches: {e}')
    try:
        archive = {}
        if os.path.exists(archive_json_path):
            with open(archive_json_path, 'r', encoding='utf-8') as f:
                archive = json.load(f)
        changed = False
        for r in results:
            if r['top_tip'] == 'N/A':
                continue
            bot_in = _bot_inputs.get(r['id'])
            bots = None
            if bot_in:
                try:
                    bots = math_engine.compute_bot_tips(score_matrix=bot_in['score_matrix'], base_xp_df=bot_in['base_xp_df'], true_probs=bot_in['true_probs'], prob_over25=bot_in['prob_over25'], home_team=r['home_team'], away_team=r['away_team'], match_id=r['id'], is_ko_phase=False)
                except Exception as e:
                    print(f"Bot tips failed for {r['id']}: {e}")
            if r['id'] not in archive:
                home_norm = TEAM_MAPPING.get(r['home_team'], r['home_team'])
                away_norm = TEAM_MAPPING.get(r['away_team'], r['away_team'])
                elo_rows_home = math_engine.elo_df.loc[math_engine.elo_df['team_name'] == home_norm, 'elo_rating']
                elo_rows_away = math_engine.elo_df.loc[math_engine.elo_df['team_name'] == away_norm, 'elo_rating']
                elo_home_val = float(elo_rows_home.values[0]) if not elo_rows_home.empty else 1500.0
                elo_away_val = float(elo_rows_away.values[0]) if not elo_rows_away.empty else 1500.0
                archive[r['id']] = {'metadata': {'home_team': r['home_team'], 'away_team': r['away_team'], 'home_disp': r['home_disp'], 'away_disp': r['away_disp'], 'is_ko_phase': False}, 'pre_match_snapshot': {'timestamp_recorded': datetime.now(timezone.utc).isoformat(), 'odds': r['odds'], 'elo_state': {'home_rating': elo_home_val, 'away_rating': elo_away_val}}, 'prediction': {'top_tip': r['top_tip'], 'user_tip': None, 'max_xp': float(r['max_xp']), 'bots': bots or {}}, 'post_match_result': {'status': 'pending', 'actual_score': None, 'points_earned': None, 'algo_points': None, 'bot_points': {k: None for k in bots or {}}}}
                changed = True
            elif bots and 'bots' not in archive[r['id']].get('prediction', {}):
                archive[r['id']]['prediction']['bots'] = bots
                pmr = archive[r['id']]['post_match_result']
                if 'bot_points' not in pmr:
                    actual = pmr.get('actual_score')
                    is_ko = archive[r['id']]['metadata'].get('is_ko_phase', False)
                    if actual:
                        pmr['bot_points'] = {bot: MathEngine.calculate_actual_points(info['tip'], actual, is_ko) for bot, info in bots.items() if info.get('tip')}
                    else:
                        pmr['bot_points'] = {k: None for k in bots}
                changed = True
        if changed:
            os.makedirs(os.path.dirname(archive_json_path), exist_ok=True)
            with open(archive_json_path, 'w', encoding='utf-8') as f:
                json.dump(archive, f, indent=4)
    except Exception as e:
        print(f'Archive logging failed: {e}')
    return results

@router.post('/api/predict')
def predict_match(payload: dict):
    math_engine.reload_elo_data()
    match_data = payload.get('match')
    is_ko = payload.get('is_ko', False)
    home_resting = payload.get('home_resting', False)
    away_resting = payload.get('away_resting', False)
    if not match_data:
        raise HTTPException(status_code=400, detail='Match data required')
    try:
        event_id = match_data.get('id', '')
        match_data = _fetch_or_cache_totals(event_id, match_data)
        math_engine.ensure_teams_exist(TEAM_MAPPING.get(match_data.get('home_team'), match_data.get('home_team')), TEAM_MAPPING.get(match_data.get('away_team'), match_data.get('away_team')))
        odds = extract_odds(match_data)
        true_probs = MathEngine.remove_margin(odds['home'], odds['draw'], odds['away'])
        b_prob_home = true_probs['home']
        b_prob_draw = true_probs['draw']
        b_prob_away = true_probs['away']
        if 'over25' in odds and 'under25' in odds:
            raw_over = 1.0 / odds['over25']
            raw_under = 1.0 / odds['under25']
            prob_over25 = raw_over / (raw_over + raw_under)
        else:
            prob_over25 = None
        elo_prob_home, elo_prob_away = math_engine.get_match_elo_probabilities(match_data.get('home_team'), match_data.get('away_team'), home_resting, away_resting)
        win_loss_pool = b_prob_home + b_prob_away
        blend_home = (b_prob_home / win_loss_pool * 0.7 + elo_prob_home * 0.3) * win_loss_pool
        blend_away = (b_prob_away / win_loss_pool * 0.7 + elo_prob_away * 0.3) * win_loss_pool
        prob_home = blend_home
        prob_away = blend_away
        prob_draw = b_prob_draw
        xg_home, xg_away = math_engine.derive_xg_from_odds(prob_home=prob_home, prob_draw=prob_draw, prob_away=prob_away, prob_over25=prob_over25)
        if is_ko:
            base_matrix = math_engine.generate_exact_score_matrix(xg_home, xg_away, max_goals=10)
            p_draw_90 = float(np.sum(np.diag(base_matrix.values)))
            et_factor = 1 + p_draw_90 / 3
            xg_home *= et_factor
            xg_away *= et_factor
        score_matrix = math_engine.generate_exact_score_matrix(xg_home, xg_away, max_goals=10)
        xp_df = math_engine.calculate_expected_points(score_matrix, is_ko_phase=is_ko)
        matrix_dict = {}
        for row in score_matrix.index:
            matrix_dict[row] = {}
            for col in score_matrix.columns:
                matrix_dict[row][col] = score_matrix.loc[row, col]
        max_prob = score_matrix.values.max()
        return {'xg_home': xg_home, 'xg_away': xg_away, 'matrix': matrix_dict, 'max_prob': max_prob, 'xp_tips': xp_df.to_dict(orient='records')}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/api/quota')
def get_quota():
    quota_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'api_quota.json')
    if os.path.exists(quota_path):
        with open(quota_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'remaining': 'Unknown', 'used': 'Unknown'}

@router.post('/api/archive/user_tip')
def set_user_tip(payload: dict):
    match_id = payload.get('match_id')
    user_tip = payload.get('user_tip', '').strip()
    if not match_id or not user_tip:
        raise HTTPException(status_code=400, detail='match_id and user_tip required')
    parts = user_tip.split(':')
    if len(parts) != 2 or not all((p.strip().isdigit() for p in parts)):
        raise HTTPException(status_code=400, detail='user_tip must be in format H:A (e.g. 2:1)')
    if not os.path.exists(archive_json_path):
        raise HTTPException(status_code=404, detail='Archive not found')
    with open(archive_json_path, 'r', encoding='utf-8') as f:
        archive = json.load(f)
    if match_id not in archive:
        raise HTTPException(status_code=404, detail='Match not in archive')
    entry = archive[match_id]
    entry['prediction']['user_tip'] = user_tip
    actual = entry['post_match_result'].get('actual_score')
    if actual:
        is_ko = entry['metadata'].get('is_ko_phase', False)
        pts = MathEngine.calculate_actual_points(user_tip, actual, is_ko)
        entry['post_match_result']['points_earned'] = pts
    else:
        pts = None
    with open(archive_json_path, 'w', encoding='utf-8') as f:
        json.dump(archive, f, indent=4)
    return {'ok': True, 'points_earned': pts}

@router.get('/api/archive')
def get_archive():
    if os.path.exists(archive_json_path):
        try:
            with open(archive_json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

@router.get('/api/elo_history')
def get_elo_history():
    history_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'elo_history.json')
    if os.path.exists(history_path):
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

@router.post('/api/sync_elo')
def sync_elo():
    try:
        return perform_elo_sync()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

