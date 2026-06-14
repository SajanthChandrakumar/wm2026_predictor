import os
import json
import time
import hashlib
from datetime import datetime
import pandas as pd
import numpy as np
import scipy.optimize as optimize
import scipy.stats as stats

HOST_NATIONS = {"United States", "Canada", "Mexico"}
HOST_ELO_BONUS = 80
DEFAULT_ELO = 1500.0


class MathEngine:
    """
    A mathematical engine for betting calculations.
    """

    def __init__(self, elo_csv_path: str, name_mapping: dict = None):
        self.elo_csv_path = elo_csv_path
        self.elo_df = pd.read_csv(elo_csv_path)
        self.elo_df['elo_rating'] = self.elo_df['elo_rating'].astype(float)
        self.name_mapping = name_mapping or {}

    @staticmethod
    def remove_margin(odds_home: float, odds_draw: float, odds_away: float) -> dict[str, float]:
        """
        Calculates the true probabilities by removing the bookmaker's margin from decimal odds.
        """
        # Calculate implied probabilities
        prob_home = 1.0 / odds_home
        prob_draw = 1.0 / odds_draw
        prob_away = 1.0 / odds_away
        
        # Calculate bookmaker's margin
        margin = prob_home + prob_draw + prob_away
        
        # Calculate true probabilities
        true_prob_home = prob_home / margin
        true_prob_draw = prob_draw / margin
        true_prob_away = prob_away / margin
        
        return {
            "home": true_prob_home,
            "draw": true_prob_draw,
            "away": true_prob_away
        }

    def get_elo_probability(self, rating_a: float, rating_b: float, is_a_host: bool = False, is_b_host: bool = False) -> float:
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

    def get_match_elo_probabilities(self, home_team: str, away_team: str, home_resting: bool = False, away_resting: bool = False) -> tuple[float, float]:
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
            
        if home_resting: elo_home -= 100
        if away_resting: elo_away -= 100

        # BEWUSST OHNE Gastgeber-Bonus (is_a_host/is_b_host).
        # Dieser Wert wird in /api/predict zu 30% mit den Buchmacher-Quoten geblendet,
        # und die Quoten preisen den Heimvorteil bereits ein. Würden wir hier zusätzlich
        # +80 Elo für USA/Kanada/Mexiko draufgeben, zählten wir den Heimvorteil doppelt
        # ("Double-Dip"). Der +80-Bonus gehört NUR in die reine Elo-Aktualisierung
        # (_calculate_new_elo), wo es keine Markt-Quote zum Gegenrechnen gibt.
        prob_home = self.get_elo_probability(elo_home, elo_away)

        return float(prob_home), float(1.0 - prob_home)

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
                new_row = pd.DataFrame([{
                    "team_code": team[:3].upper(),
                    "team_name": team,
                    "elo_rating": 1500.0,
                }])
                self.elo_df = pd.concat([self.elo_df, new_row], ignore_index=True)
                added = True
        if added:
            self.elo_df.to_csv(self.elo_csv_path, index=False)

    @staticmethod
    def derive_xg_from_odds(prob_home: float, prob_draw: float, prob_away: float, prob_over25: float = None) -> tuple[float, float]:
        """
        Derives Expected Goals (xG) for home and away teams by minimizing the difference
        between bookmaker probabilities and Poisson-derived probabilities.
        prob_over25 is optional — omit when totals market data is unavailable.
        """
        def cost_function(lambdas):
            l_home, l_away = lambdas

            max_goals = 10
            poisson_home = stats.poisson.pmf(np.arange(max_goals), l_home)
            poisson_away = stats.poisson.pmf(np.arange(max_goals), l_away)

            prob_matrix = np.outer(poisson_home, poisson_away)

            rho = -0.15
            prob_matrix[0, 0] *= 1 - (l_home * l_away * rho)
            prob_matrix[1, 0] *= 1 + (l_home * rho)
            prob_matrix[0, 1] *= 1 + (l_away * rho)
            prob_matrix[1, 1] *= 1 - rho

            prob_matrix = prob_matrix / np.sum(prob_matrix)

            calc_home = np.sum(np.tril(prob_matrix, -1))
            calc_draw = np.sum(np.diag(prob_matrix))
            calc_away = np.sum(np.triu(prob_matrix, 1))

            error = (
                (calc_home - prob_home) ** 2 +
                (calc_draw - prob_draw) ** 2 +
                (calc_away - prob_away) ** 2
            )

            if prob_over25 is not None:
                goals_h, goals_a = np.indices((max_goals, max_goals))
                calc_over25 = np.sum(prob_matrix[(goals_h + goals_a) > 2])
                error += (calc_over25 - prob_over25) ** 2

            return error

        bounds = ((0.1, 5.0), (0.1, 5.0))

        result = optimize.minimize(cost_function, [1.5, 1.5], bounds=bounds, method='L-BFGS-B')
        if not result.success:
            result = optimize.minimize(cost_function, [prob_home * 3.5, prob_away * 3.5], bounds=bounds, method='L-BFGS-B')

        if not result.success:
            # Proportional fallback: scale world-cup averages by the match's win probability ratio
            l_home = max(0.1, min(5.0, 1.35 * (prob_home / 0.45)))
            l_away = max(0.1, min(5.0, 1.10 * (prob_away / 0.28)))
            return l_home, l_away

        return float(result.x[0]), float(result.x[1])

    @staticmethod
    def generate_exact_score_matrix(lambda_home: float, lambda_away: float, max_goals: int = 5, rho: float = -0.15) -> pd.DataFrame:
        """
        Generates a matrix of exact score probabilities using independent Poisson distributions,
        adjusted with the Dixon-Coles method for low-scoring draws.
        """
        goals_range = np.arange(max_goals + 1)
        prob_home = stats.poisson.pmf(goals_range, lambda_home)
        prob_away = stats.poisson.pmf(goals_range, lambda_away)
        
        # Joint probability matrix
        prob_matrix = np.outer(prob_home, prob_away)
        
        # Dixon-Coles adjustment
        tau_00 = 1 - (lambda_home * lambda_away * rho)
        tau_10 = 1 + (lambda_home * rho)
        tau_01 = 1 + (lambda_away * rho)
        tau_11 = 1 - rho
        
        prob_matrix[0, 0] *= tau_00
        prob_matrix[1, 0] *= tau_10
        prob_matrix[0, 1] *= tau_01
        prob_matrix[1, 1] *= tau_11
        
        # Normalize matrix
        prob_matrix = prob_matrix / np.sum(prob_matrix)
        
        # Create DataFrame
        df = pd.DataFrame(
            prob_matrix,
            index=[f"{g}" for g in goals_range],
            columns=[f"{g}" for g in goals_range]
        )
        df.index.name = "Home Goals"
        df.columns.name = "Away Goals"
        return df

    @staticmethod
    def calculate_actual_points(tipped_score: str, actual_score: str, is_ko_phase: bool = False) -> int:
        """Score a completed tip against an actual result using the SRF Tippspiel ruleset."""
        try:
            t_home, t_away = map(int, tipped_score.split(":"))
            a_home, a_away = map(int, actual_score.split(":"))
        except Exception:
            return 0

        points = 0
        t_tend = np.sign(t_home - t_away)
        a_tend = np.sign(a_home - a_away)
        tendency_correct = t_tend == a_tend

        if tendency_correct:
            points += 5
        if t_home == a_home:
            points += 1
        if t_away == a_away:
            points += 1
        if tendency_correct and (t_home - t_away) == (a_home - a_away):
            points += 3

        return points * 2 if is_ko_phase else points

    @staticmethod
    def _tip_points(tipped_home: int, tipped_away: int, actual_home: int, actual_away: int, is_ko_phase: bool = False) -> int:
        return MathEngine.calculate_actual_points(
            f"{tipped_home}:{tipped_away}", f"{actual_home}:{actual_away}", is_ko_phase
        )

    def _points_distribution(self, t_home: int, t_away: int, score_matrix: pd.DataFrame, is_ko_phase: bool) -> tuple[float, float]:
        """Gibt (Erwartungswert, Standardabweichung) der Punkte eines Tipps über die Resultatverteilung zurück."""
        ev = 0.0
        ev_sq = 0.0
        for a_home_str in score_matrix.index:
            for a_away_str in score_matrix.columns:
                prob = score_matrix.loc[a_home_str, a_away_str]
                if prob > 0:
                    pts = self._tip_points(t_home, t_away, int(a_home_str), int(a_away_str), is_ko_phase)
                    ev += pts * prob
                    ev_sq += (pts ** 2) * prob
        variance = max(0.0, ev_sq - ev ** 2)
        return ev, variance ** 0.5

    def calculate_expected_points(self, score_matrix: pd.DataFrame, is_ko_phase: bool = False, top_n: int = 5) -> pd.DataFrame:
        """
        Calculates the Expected Points (xP) for tips from 0:0 up to 5:5 based on the specific ruleset.
        """
        results = []
        max_tip_goals = 5

        for t_home in range(max_tip_goals + 1):
            for t_away in range(max_tip_goals + 1):
                xp, _ = self._points_distribution(t_home, t_away, score_matrix, is_ko_phase)
                results.append({"Tipp": f"{t_home}:{t_away}", "xP": xp})

        df_xp = pd.DataFrame(results)
        df_xp = df_xp.sort_values(by="xP", ascending=False).head(top_n).reset_index(drop=True)
        return df_xp

    def compute_bot_tips(
        self,
        score_matrix: pd.DataFrame,
        true_probs: dict,
        prob_over25,
        home_team: str,
        away_team: str,
        match_id: str,
        is_ko_phase: bool = False,
        chalk_tip: str = None,
        chalk_xp: float = None,
    ) -> dict:
        """
        Compute tips for all 5 prediction bots. Returns dict keyed by bot name.
        score_matrix is the already-blended 70/30 Elo-odds matrix.
        true_probs are the bookmaker-only probabilities (margin removed).
        chalk_tip / chalk_xp are passed in directly from the already-computed top_tip.
        """
        bots = {}

        # 1. chalk — reuse pre-computed top_tip (no recomputation)
        bots["chalk"] = {"tip": chalk_tip, "xp": round(chalk_xp, 4) if chalk_xp is not None else None}

        # 2. odds_pure — 100% bookmaker odds, 0% Elo
        try:
            xg_h, xg_a = self.derive_xg_from_odds(
                true_probs["home"], true_probs["draw"], true_probs["away"], prob_over25
            )
            sm_odds = self.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
            df_odds = self.calculate_expected_points(sm_odds, is_ko_phase=is_ko_phase)
            bots["odds_pure"] = {
                "tip": df_odds.iloc[0]["Tipp"] if not df_odds.empty else None,
                "xp": round(float(df_odds.iloc[0]["xP"]), 4) if not df_odds.empty else None,
            }
        except Exception:
            bots["odds_pure"] = {"tip": None, "xp": None}

        # 3. elo_pure — 100% Elo, 0% odds
        # get_match_elo_probabilities returns (p_home, p_away) that sum to 1.
        # We apply a minimum draw floor of 0.15 and rescale win/loss accordingly.
        try:
            elo_p_home, elo_p_away = self.get_match_elo_probabilities(home_team, away_team)
            prob_draw_elo = max(0.15, 1.0 - elo_p_home - elo_p_away)  # = max(0.15, 0) = 0.15
            scale = 1.0 - prob_draw_elo
            xg_h, xg_a = self.derive_xg_from_odds(
                elo_p_home * scale, prob_draw_elo, elo_p_away * scale, None
            )
            sm_elo = self.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
            df_elo = self.calculate_expected_points(sm_elo, is_ko_phase=is_ko_phase)
            bots["elo_pure"] = {
                "tip": df_elo.iloc[0]["Tipp"] if not df_elo.empty else None,
                "xp": round(float(df_elo.iloc[0]["xP"]), 4) if not df_elo.empty else None,
            }
        except Exception:
            bots["elo_pure"] = {"tip": None, "xp": None}

        # 4. draw_hunter — from top-10, pick draw if P(draw) > 0.25, else chalk
        try:
            df_top10 = self.calculate_expected_points(score_matrix, is_ko_phase=is_ko_phase, top_n=10)
            p_draw_matrix = float(np.sum(np.diag(score_matrix.values)))
            draw_tip = None
            if p_draw_matrix > 0.25:
                for _, row in df_top10.iterrows():
                    h, a = row["Tipp"].split(":")
                    if h == a:
                        draw_tip = (row["Tipp"], round(float(row["xP"]), 4))
                        break
            if draw_tip:
                bots["draw_hunter"] = {"tip": draw_tip[0], "xp": draw_tip[1]}
            else:
                bots["draw_hunter"] = {"tip": chalk_tip, "xp": round(chalk_xp, 4) if chalk_xp is not None else None}
        except Exception:
            bots["draw_hunter"] = {"tip": chalk_tip, "xp": round(chalk_xp, 4) if chalk_xp is not None else None}

        # 5. random — weighted sample from top-10, seeded by match_id for reproducibility
        try:
            df_top10 = self.calculate_expected_points(score_matrix, is_ko_phase=is_ko_phase, top_n=10)
            seed = int(hashlib.md5(match_id.encode()).hexdigest()[:8], 16) % (2 ** 31)
            rng = np.random.default_rng(seed)
            weights = df_top10["xP"].values.astype(float)
            weights = np.maximum(weights, 0)
            weights = weights / weights.sum()
            idx = int(rng.choice(len(df_top10), p=weights))
            bots["random"] = {
                "tip": df_top10.iloc[idx]["Tipp"],
                "xp": round(float(df_top10.iloc[idx]["xP"]), 4),
            }
        except Exception:
            bots["random"] = {"tip": chalk_tip, "xp": round(chalk_xp, 4) if chalk_xp is not None else None}

        return bots

    def _calculate_new_elo(self, rating_a: float, rating_b: float, actual_result_a: float, k_factor: int = 60, is_a_host: bool = False, is_b_host: bool = False, goal_diff: int = 0) -> tuple[float, float]:
        """
        Standard Elo update. K=60 entspricht dem World-Football-Elo-Standard
        für WM-Endrundenspiele; der Margin-of-Victory-Multiplikator ebenso
        (×1.5 bei 2 Toren Differenz, ×1.75 bei 3, +1/8 je weiteres Tor).
        """
        expected_a = self.get_elo_probability(rating_a, rating_b, is_a_host=is_a_host, is_b_host=is_b_host)
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
        new_rating_b = rating_b + k * ((1 - actual_result_a) - expected_b)
        return new_rating_a, new_rating_b

    def update_elo_from_api_scores(self, api_scores: list, processed_matches_file: str = 'data/processed_matches.json') -> int:
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
            match_id = match.get("id")
            if not match_id or match_id in processed_set or not match.get("completed"):
                continue
                
            home_team = match.get("home_team")
            away_team = match.get("away_team")
            scores = match.get("scores")
            
            if not scores:
                continue
                
            # Parse scores
            home_score = next((s["score"] for s in scores if s["name"] == home_team), None)
            away_score = next((s["score"] for s in scores if s["name"] == away_team), None)
            
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
                        new_row = pd.DataFrame([{"team_code": team[:3].upper(), "team_name": team, "elo_rating": 1500}])
                        self.elo_df = pd.concat([self.elo_df, new_row], ignore_index=True)
                        
                elo_home = self.elo_df.loc[self.elo_df['team_name'] == home_norm, 'elo_rating'].values[0]
                elo_away = self.elo_df.loc[self.elo_df['team_name'] == away_norm, 'elo_rating'].values[0]
                    
                hosts = ["United States", "Canada", "Mexico"]
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
                
                # Elo History Logging
                history_json_path = os.path.join(os.path.dirname(os.path.abspath(processed_matches_file)), 'elo_history.json')
                history = {}
                if os.path.exists(history_json_path):
                    try:
                        with open(history_json_path, 'r', encoding='utf-8') as hf:
                            history = json.load(hf)
                    except json.JSONDecodeError:
                        history = {}
                
                for team_name, new_elo in [(home_norm, new_elo_home), (away_norm, new_elo_away)]:
                    if team_name not in history:
                        # Insert baseline entry using current CSV value before this update
                        baseline_rows = self.elo_df.loc[self.elo_df['team_name'] == team_name, 'elo_rating']
                        baseline_elo = float(baseline_rows.values[0]) if not baseline_rows.empty else 1500.0
                        history[team_name] = [
                            {"timestamp": 0, "match_id": "baseline", "elo": baseline_elo}
                        ]
                    history[team_name].append({
                        "timestamp": float(time.time()),
                        "match_id": str(match_id),
                        "elo": float(new_elo)
                    })
                
                try:
                    with open(history_json_path, 'w', encoding='utf-8') as hf:
                        json.dump(history, hf, indent=4)
                except Exception as e:
                    print(f"Failed to write Elo history: {e}")
                
                processed_set.add(match_id)
                processed_ids.append(match_id)
                updates_made += 1
                
        if updates_made > 0:
            os.makedirs(os.path.dirname(os.path.abspath(processed_matches_file)), exist_ok=True)
            with open(processed_matches_file, 'w', encoding='utf-8') as f:
                json.dump(processed_ids, f, indent=4)

        return updates_made

    def _get_historical_elo(self, team_name: str, before_ts: float = None) -> float:
        """
        Liefert die Elo eines Teams VOR einem Zeitpunkt.
        Quelle: elo_history.json im selben data/-Ordner wie elo_csv_path.
        Fallback DEFAULT_ELO (1500), wenn das Team nicht in der History steht.
        """
        norm = self.name_mapping.get(team_name, team_name)
        history_path = os.path.join(os.path.dirname(self.elo_csv_path), 'elo_history.json')
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

    def reconstruct_algo_tip(
        self,
        home_team: str,
        away_team: str,
        commence_time: str = None,
        is_ko: bool = False,
    ) -> tuple:
        """
        Rekonstruiert einen Algo-Tipp für ein Match ohne historische Quoten
        (z. B. wenn das Match vor App-Start lief). Pipeline: historische
        Pre-Match-Elo → H/D/A (heuristische Draw-Rate) → xG → Score-Matrix →
        Top-xP-Tipp. commence_time im ISO-Format; None → Baseline-Elo.
        Returns (tip_str, max_xp) oder (None, None) bei Fehler.
        """
        before_ts = None
        if commence_time:
            try:
                before_ts = datetime.fromisoformat(
                    commence_time.replace("Z", "+00:00")
                ).timestamp()
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

        # Elo → Win-Loss-Pool. Draw-Rate heuristisch:
        # 0.28 bei gleicher Elo, sinkt linear mit |ΔElo|, Boden 0.18.
        p_home_winloss = self.get_elo_probability(elo_home, elo_away)
        diff = abs(elo_home - elo_away)
        p_draw = max(0.18, 0.28 - (diff / 1000) * 0.10)
        p_home = p_home_winloss * (1.0 - p_draw)
        p_away = (1.0 - p_home_winloss) * (1.0 - p_draw)

        try:
            xg_h, xg_a = self.derive_xg_from_odds(p_home, p_draw, p_away, prob_over25=None)
        except Exception:
            return None, None

        if is_ko:
            base_matrix = self.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
            p_draw_90 = float(np.sum(np.diag(base_matrix.values)))
            et_factor = 1 + p_draw_90 / 3
            xg_h *= et_factor
            xg_a *= et_factor

        score_matrix = self.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
        xp_df = self.calculate_expected_points(score_matrix, is_ko_phase=is_ko)

        if xp_df.empty:
            return None, None
        return xp_df.iloc[0]['Tipp'], float(xp_df.iloc[0]['xP'])
