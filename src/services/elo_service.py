from src.core import math
from src.core import config as math_core
from src.services import prediction_service
import os
import json
import time
import hashlib
from datetime import datetime
import pandas as pd
import numpy as np
import scipy.optimize as optimize
import scipy.stats as stats
HOST_NATIONS = {'United States', 'Canada', 'Mexico'}
HOST_ELO_BONUS = 80
DEFAULT_ELO = 1500.0

class EloService:
    """
    A mathematical engine for betting calculations.
    """

    def __init__(self, elo_csv_path: str, name_mapping: dict=None):
        self.elo_csv_path = elo_csv_path
        self.elo_df = pd.read_csv(elo_csv_path)
        self.elo_df['elo_rating'] = self.elo_df['elo_rating'].astype(float)
        self.name_mapping = name_mapping or {}
        self.team_forms = {}

    def get_elo_probability(self, rating_a: float, rating_b: float, is_a_host: bool=False, is_b_host: bool=False) -> float:
        """Berechnet die reine Elo-Siegwahrscheinlichkeit für Team A inkl. möglichem Heimvorteil."""
        if is_a_host:
            rating_a += 80
        if is_b_host:
            rating_b += 80
        diff = rating_a - rating_b
        return 1 / (10 ** (-diff / 400) + 1)

    def reload_elo_data(self):
        """ Reloads the latest Elo dataframe from the CSV file to ensure global state is up-to-date """
        if os.path.exists(self.elo_csv_path):
            self.elo_df = pd.read_csv(self.elo_csv_path)
            self.elo_df['elo_rating'] = self.elo_df['elo_rating'].astype(float)
        self._build_team_forms()

    def _build_team_forms(self):
        """
        Reconstructs the W-D-L visual form chain for all teams based on elo_history.json
        and prediction_archive.json.
        """
        import json
        import os
        history_path = config.ELO_HISTORY_PATH
        archive_path = os.path.join(os.path.dirname(self.elo_csv_path), 'prediction_archive.json')
        if not os.path.exists(history_path) or not os.path.exists(archive_path):
            self.team_forms = {}
            return
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                elo_hist = json.load(f)
            with open(archive_path, 'r', encoding='utf-8') as f:
                archive = json.load(f)
        except Exception:
            self.team_forms = {}
            return
        forms = {}
        for team_name, entries in elo_hist.items():
            team_form = []
            prev_elo = entries[0]['elo'] if entries else 1500.0
            for i in range(1, len(entries)):
                entry = entries[i]
                curr_elo = entry['elo']
                match_id = entry['match_id']
                if match_id == 'baseline' or match_id not in archive:
                    prev_elo = curr_elo
                    continue
                match = archive[match_id]
                res = match.get('post_match_result', {})
                if res.get('status') != 'completed':
                    prev_elo = curr_elo
                    continue
                actual_score = res.get('actual_score')
                if not actual_score or actual_score == 'N/A':
                    prev_elo = curr_elo
                    continue
                try:
                    h_goals, a_goals = map(int, actual_score.split(':'))
                except ValueError:
                    prev_elo = curr_elo
                    continue
                home_team = match.get('metadata', {}).get('home_team', '')
                home_norm = self.name_mapping.get(home_team, home_team)
                if team_name == home_norm:
                    opp = match.get('metadata', {}).get('away_disp', 'Unknown')
                    gf, ga = (h_goals, a_goals)
                else:
                    opp = match.get('metadata', {}).get('home_disp', 'Unknown')
                    gf, ga = (a_goals, h_goals)
                if gf > ga:
                    outcome = 'W'
                elif gf < ga:
                    outcome = 'L'
                else:
                    outcome = 'D'
                delta = curr_elo - prev_elo
                team_form.append({'result': outcome, 'opponent': opp, 'score': f'{gf}:{ga}', 'delta': round(delta, 1)})
                prev_elo = curr_elo
            last_5 = team_form[-5:]
            on_fire = False
            if len(last_5) >= 3 and all((f['result'] == 'W' for f in last_5[-3:])):
                on_fire = True
            elif len(last_5) >= 2 and sum((f['delta'] for f in last_5[-2:])) >= 40:
                on_fire = True
            forms[team_name] = {'form': last_5, 'on_fire': on_fire}
        self.team_forms = forms

    def get_match_elo_probabilities(self, home_team: str, away_team: str, home_resting: bool=False, away_resting: bool=False) -> tuple[float, float]:
        home_norm = self.name_mapping.get(home_team, home_team)
        away_norm = self.name_mapping.get(away_team, away_team)
        if home_norm in self.elo_df['team_name'].values:
            elo_home = self.elo_df.loc[self.elo_df['team_name'] == home_norm, 'elo_rating'].values[0]
        else:
            elo_home = 1500.0
        if away_norm in self.elo_df['team_name'].values:
            elo_away = self.elo_df.loc[self.elo_df['team_name'] == away_norm, 'elo_rating'].values[0]
        else:
            elo_away = 1500.0
        if home_resting:
            elo_home -= 100
        if away_resting:
            elo_away -= 100
        prob_home = math_core.get_elo_probability(elo_home, elo_away)
        return (float(prob_home), float(1.0 - prob_home))

    def ensure_teams_exist(self, *teams: str) -> None:
        """
        Stellt sicher, dass jedes (bereits normalisierte) Team eine Zeile im
        Elo-DataFrame hat — fehlende Teams werden mit Default-Elo 1500 angelegt
        und persistiert. Explizit benannter Side-Effect statt versteckt in einer
        'merge'-Funktion. Keine Rückgabe.
        """
        added = False
        for team in teams:
            if team and team not in self.elo_df['team_name'].values:
                new_row = pd.DataFrame([{'team_code': team[:3].upper(), 'team_name': team, 'elo_rating': 1500.0}])
                self.elo_df = pd.concat([self.elo_df, new_row], ignore_index=True)
                added = True
        if added:
            self.elo_df.to_csv(self.elo_csv_path, index=False)

    def _calculate_new_elo(self, rating_a: float, rating_b: float, actual_result_a: float, k_factor: int=60, is_a_host: bool=False, is_b_host: bool=False, goal_diff: int=0) -> tuple[float, float]:
        """
        Standard Elo update. K=60 entspricht dem World-Football-Elo-Standard
        für WM-Endrundenspiele; der Margin-of-Victory-Multiplikator ebenso
        (×1.5 bei 2 Toren Differenz, ×1.75 bei 3, +1/8 je weiteres Tor).
        """
        expected_a = math_core.get_elo_probability(rating_a, rating_b, is_a_host=is_a_host, is_b_host=is_b_host)
        expected_b = 1 - expected_a
        gd = abs(goal_diff)
        if gd <= 1:
            mov_multiplier = 1.0
        elif gd == 2:
            mov_multiplier = 1.5
        else:
            mov_multiplier = 1.75 + (gd - 3) / 8
        k = k_factor * mov_multiplier
        new_rating_a = rating_a + k * (actual_result_a - expected_a)
        new_rating_b = rating_b + k * (1 - actual_result_a - expected_b)
        return (new_rating_a, new_rating_b)

    def update_elo_from_api_scores(self, api_scores: list, processed_matches_file: str='data/processed_matches.json') -> int:
        """
        Updates Elo ratings based on completed matches from the API, 
        ensuring idempotency by tracking processed match IDs.
        """
        processed_ids = []
        if os.path.exists(processed_matches_file):
            with open(processed_matches_file, 'r', encoding='utf-8') as f:
                try:
                    processed_ids = json.load(f)
                except json.JSONDecodeError:
                    processed_ids = []
        processed_set = set(processed_ids)
        updates_made = 0
        for match in api_scores:
            match_id = match.get('id')
            if not match_id or match_id in processed_set or (not match.get('completed')):
                continue
            home_team = match.get('home_team')
            away_team = match.get('away_team')
            scores = match.get('scores')
            if not scores:
                continue
            home_score = next((s['score'] for s in scores if s['name'] == home_team), None)
            away_score = next((s['score'] for s in scores if s['name'] == away_team), None)
            if home_score is not None and away_score is not None:
                try:
                    home_score = int(home_score)
                    away_score = int(away_score)
                except ValueError:
                    continue
                home_norm = self.name_mapping.get(home_team, home_team)
                away_norm = self.name_mapping.get(away_team, away_team)
                for team in [home_norm, away_norm]:
                    if team not in self.elo_df['team_name'].values:
                        new_row = pd.DataFrame([{'team_code': team[:3].upper(), 'team_name': team, 'elo_rating': 1500}])
                        self.elo_df = pd.concat([self.elo_df, new_row], ignore_index=True)
                elo_home = self.elo_df.loc[self.elo_df['team_name'] == home_norm, 'elo_rating'].values[0]
                elo_away = self.elo_df.loc[self.elo_df['team_name'] == away_norm, 'elo_rating'].values[0]
                hosts = ['United States', 'Canada', 'Mexico']
                is_home_host = home_norm in hosts
                is_away_host = away_norm in hosts
                if home_score > away_score:
                    result_home = 1.0
                elif home_score < away_score:
                    result_home = 0.0
                else:
                    result_home = 0.5
                new_elo_home, new_elo_away = self._calculate_new_elo(elo_home, elo_away, result_home, is_a_host=is_home_host, is_b_host=is_away_host, goal_diff=home_score - away_score)
                self.elo_df.loc[self.elo_df['team_name'] == home_norm, 'elo_rating'] = float(new_elo_home)
                self.elo_df.loc[self.elo_df['team_name'] == away_norm, 'elo_rating'] = float(new_elo_away)
                history_json_path = config.ELO_HISTORY_PATH
                history = {}
                if os.path.exists(history_json_path):
                    try:
                        with open(history_json_path, 'r', encoding='utf-8') as hf:
                            history = json.load(hf)
                    except json.JSONDecodeError:
                        history = {}
                for team_name, new_elo in [(home_norm, new_elo_home), (away_norm, new_elo_away)]:
                    if team_name not in history:
                        baseline_rows = self.elo_df.loc[self.elo_df['team_name'] == team_name, 'elo_rating']
                        baseline_elo = float(baseline_rows.values[0]) if not baseline_rows.empty else 1500.0
                        history[team_name] = [{'timestamp': 0, 'match_id': 'baseline', 'elo': baseline_elo}]
                    history[team_name].append({'timestamp': float(time.time()), 'match_id': str(match_id), 'elo': float(new_elo)})
                try:
                    with open(history_json_path, 'w', encoding='utf-8') as hf:
                        json.dump(history, hf, indent=4)
                except Exception as e:
                    print(f'Failed to write Elo history: {e}')
                processed_set.add(match_id)
                processed_ids.append(match_id)
                updates_made += 1
        if updates_made > 0:
            os.makedirs(os.path.dirname(os.path.abspath(processed_matches_file)), exist_ok=True)
            with open(processed_matches_file, 'w', encoding='utf-8') as f:
                json.dump(processed_ids, f, indent=4)
        return updates_made

    def _get_historical_elo(self, team_name: str, before_ts: float=None) -> float:
        """
        Liefert die Elo eines Teams VOR einem Zeitpunkt.
        Quelle: elo_history.json im selben data/-Ordner wie elo_csv_path.
        Fallback DEFAULT_ELO (1500), wenn das Team nicht in der History steht.
        """
        norm = self.name_mapping.get(team_name, team_name)
        history_path = config.ELO_HISTORY_PATH
        if not os.path.exists(history_path):
            return DEFAULT_ELO
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except (json.JSONDecodeError, OSError):
            return DEFAULT_ELO
        team_history = history.get(norm, [])
        if not team_history:
            return DEFAULT_ELO
        if before_ts is None:
            return float(team_history[0]['elo'])
        valid = [e for e in team_history if e.get('timestamp', 0) < before_ts]
        if not valid:
            return float(team_history[0]['elo'])
        return float(valid[-1]['elo'])

    def _reconstruct_pipeline(self, home_team: str, away_team: str, commence_time: str=None, is_ko: bool=False):
        """
        Pipeline: historische Pre-Match-Elo → H/D/A → xG → Score-Matrix → Top-xP-Tipp.
        Returns (score_matrix, p_home, p_draw, p_away, tip, xp) — alle None bei Fehler.
        """
        before_ts = None
        if commence_time:
            try:
                before_ts = datetime.fromisoformat(commence_time.replace('Z', '+00:00')).timestamp()
            except ValueError:
                before_ts = None
        elo_home = self._get_historical_elo(home_team, before_ts)
        elo_away = self._get_historical_elo(away_team, before_ts)
        home_norm = self.name_mapping.get(home_team, home_team)
        away_norm = self.name_mapping.get(away_team, away_team)
        if home_norm in HOST_NATIONS:
            elo_home += HOST_ELO_BONUS
        if away_norm in HOST_NATIONS:
            elo_away += HOST_ELO_BONUS
        p_home_winloss = math_core.get_elo_probability(elo_home, elo_away)
        diff = abs(elo_home - elo_away)
        p_draw = max(0.18, 0.28 - diff / 1000 * 0.1)
        p_home = p_home_winloss * (1.0 - p_draw)
        p_away = (1.0 - p_home_winloss) * (1.0 - p_draw)
        try:
            xg_h, xg_a = math_core.derive_xg_from_odds(p_home, p_draw, p_away, prob_over25=None)
        except Exception:
            return (None, None, None, None, None, None)
        if is_ko:
            base_matrix = math_core.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
            p_draw_90 = float(np.sum(np.diag(base_matrix.values)))
            et_factor = 1 + p_draw_90 / 3
            xg_h *= et_factor
            xg_a *= et_factor
        score_matrix = math_core.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
        xp_df = math_core.calculate_expected_points(score_matrix, is_ko_phase=is_ko, math_core=math_core, elo_service=self)
        if xp_df.empty:
            return (None, None, None, None, None, None)
        return (score_matrix, p_home, p_draw, p_away, xp_df.iloc[0]['Tipp'], float(xp_df.iloc[0]['xP']))

    def reconstruct_algo_tip(self, home_team: str, away_team: str, commence_time: str=None, is_ko: bool=False) -> tuple:
        """
        Rekonstruiert einen Algo-Tipp für ein Match ohne historische Quoten
        (z. B. wenn das Match vor App-Start lief). Returns (tip, max_xp).
        """
        _, _, _, _, tip, xp = self._reconstruct_pipeline(home_team, away_team, commence_time, is_ko)
        return (tip, xp)

    def reconstruct_bot_tips(self, home_team: str, away_team: str, match_id: str, commence_time: str=None, is_ko: bool=False) -> dict | None:
        """
        Bot-Tipps für ein Match ohne historische Quoten. odds_pure ist
        semantisch nicht definiert ohne Quoten — fällt deshalb auf die
        Elo-Wahrscheinlichkeiten als "true_probs" zurück (was für diese Matches
        odds_pure ≈ elo_pure ≈ chalk macht).
        """
        sm, p_home, p_draw, p_away, tip, xp = self._reconstruct_pipeline(home_team, away_team, commence_time, is_ko)
        if sm is None:
            return None
        true_probs = {'home': p_home, 'draw': p_draw, 'away': p_away}
        base_xp_df = math_core.calculate_expected_points(sm, is_ko_phase=is_ko, math_core=math_core, elo_service=self)
        return prediction_service.compute_bot_tips(score_matrix=sm, base_xp_df=base_xp_df, true_probs=true_probs, prob_over25=None, home_team=home_team, away_team=away_team, match_id=match_id, is_ko_phase=is_ko, math_core=math_core, elo_service=self)
def perform_elo_sync() -> dict:
    print('Automated Elo sync triggered...')
    odds_engine = OddsApiEngine()
    processed_json_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed_matches.json')
    try:
        scores_cache = {}
        if os.path.exists(scores_cache_path):
            try:
                with open(scores_cache_path, 'r', encoding='utf-8') as f:
                    scores_cache = json.load(f)
            except Exception:
                pass
        if time.time() - scores_cache.get('timestamp', 0) < SCORES_CACHE_TTL:
            completed_matches = scores_cache.get('data', [])
            print('Elo sync: using cached scores (< 30 min old)')
        else:
            completed_matches = odds_engine.get_completed_scores(days_from=3)
            try:
                os.makedirs(os.path.dirname(scores_cache_path), exist_ok=True)
                with open(scores_cache_path, 'w', encoding='utf-8') as f:
                    json.dump({'timestamp': time.time(), 'data': completed_matches}, f, indent=4)
            except Exception as e:
                print(f'Scores cache write failed: {e}')
        updates = math_engine.update_elo_from_api_scores(api_scores=completed_matches, processed_matches_file=processed_json_path)
        if updates > 0:
            math_engine.elo_df.to_csv(math_engine.elo_csv_path, index=False)
            print(f'Automated Elo sync completed: {updates} updates.')
        try:
            archive = {}
            if os.path.exists(archive_json_path):
                with open(archive_json_path, 'r', encoding='utf-8') as f:
                    archive = json.load(f)
            graded = 0
            retro = 0
            for match in completed_matches:
                match_id = match.get('id')
                if not match_id or not match.get('completed'):
                    continue
                home_team = match.get('home_team')
                away_team = match.get('away_team')
                scores = match.get('scores') or []
                home_score = next((s['score'] for s in scores if s['name'] == home_team), None)
                away_score = next((s['score'] for s in scores if s['name'] == away_team), None)
                if home_score is None or away_score is None:
                    continue
                try:
                    home_score = int(home_score)
                    away_score = int(away_score)
                except ValueError:
                    continue
                actual_score_str = f'{home_score}:{away_score}'
                if match_id not in archive:
                    archive[match_id] = {'metadata': {'home_team': home_team, 'away_team': away_team, 'home_disp': DISPLAY_MAPPING.get(home_team, home_team), 'away_disp': DISPLAY_MAPPING.get(away_team, away_team), 'is_ko_phase': False}, 'pre_match_snapshot': None, 'prediction': {'top_tip': None, 'max_xp': None}, 'post_match_result': {'status': 'completed', 'actual_score': actual_score_str, 'points_earned': None}}
                    retro += 1
                    continue
                if archive[match_id]['post_match_result']['status'] != 'pending':
                    continue
                algo_tip = archive[match_id]['prediction'].get('top_tip')
                user_tip = archive[match_id]['prediction'].get('user_tip')
                is_ko = archive[match_id]['metadata']['is_ko_phase']
                active_tip = user_tip if user_tip else algo_tip
                archive[match_id]['post_match_result']['status'] = 'completed'
                archive[match_id]['post_match_result']['actual_score'] = actual_score_str
                archive[match_id]['post_match_result']['points_earned'] = MathEngine.calculate_actual_points(active_tip, actual_score_str, is_ko) if active_tip else None
                archive[match_id]['post_match_result']['algo_points'] = MathEngine.calculate_actual_points(algo_tip, actual_score_str, is_ko) if algo_tip else None
                bots = archive[match_id]['prediction'].get('bots', {})
                if bots:
                    archive[match_id]['post_match_result']['bot_points'] = {bot: MathEngine.calculate_actual_points(info['tip'], actual_score_str, is_ko) for bot, info in bots.items() if info.get('tip')}
                graded += 1
            ct_map = {m.get('id'): m.get('commence_time') for m in completed_matches}
            reconstructed = 0
            for mid, entry in archive.items():
                if entry.get('post_match_result', {}).get('status') != 'completed':
                    continue
                if entry.get('pre_match_snapshot') is not None:
                    continue
                actual = entry.get('post_match_result', {}).get('actual_score')
                if not actual:
                    continue
                home = entry['metadata']['home_team']
                away = entry['metadata']['away_team']
                is_ko_match = entry['metadata'].get('is_ko_phase', False)
                bots = math_engine.reconstruct_bot_tips(home, away, str(mid), commence_time=ct_map.get(mid), is_ko=is_ko_match)
                if not bots:
                    continue
                tip = bots['professor']['tip']
                max_xp = bots['professor'].get('xp', 0)
                if not tip:
                    continue
                already_done = entry['prediction'].get('top_tip') == tip and entry['prediction'].get('algo_reconstructed') is True and entry['prediction'].get('bots')
                if already_done:
                    continue
                entry['prediction']['top_tip'] = tip
                entry['prediction']['max_xp'] = max_xp
                entry['prediction']['algo_reconstructed'] = True
                entry['prediction']['bots'] = bots
                entry['post_match_result']['algo_points'] = MathEngine.calculate_actual_points(tip, actual, is_ko_match)
                entry['post_match_result']['bot_points'] = {name: MathEngine.calculate_actual_points(info['tip'], actual, is_ko_match) for name, info in bots.items() if info.get('tip')}
                user_tip = entry['prediction'].get('user_tip')
                if user_tip:
                    entry['post_match_result']['points_earned'] = MathEngine.calculate_actual_points(user_tip, actual, is_ko_match)
                reconstructed += 1
            if graded > 0 or retro > 0 or reconstructed > 0:
                os.makedirs(os.path.dirname(archive_json_path), exist_ok=True)
                with open(archive_json_path, 'w', encoding='utf-8') as f:
                    json.dump(archive, f, indent=4)
                if graded:
                    print(f'Archive grading completed: {graded} predictions scored.')
                if retro:
                    print(f'Retroactive archive entries created: {retro} matches.')
                if reconstructed:
                    print(f'Algo tips reconstructed: {reconstructed} matches (Elo-only pipeline).')
        except Exception as e:
            print(f'Archive grading failed: {e}')
        if updates > 0:
            return {'status': 'success', 'updates': updates}
        else:
            print('Automated Elo sync completed: No new matches.')
            return {'status': 'info', 'message': 'No new matches.'}
    except Exception as e:
        print(f'Automated Elo sync failed: {str(e)}')
        raise e
