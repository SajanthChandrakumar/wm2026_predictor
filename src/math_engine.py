import os
import json
import time
import pandas as pd
import numpy as np
import scipy.optimize as optimize
import scipy.stats as stats

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

    def calculate_expected_points(self, score_matrix: pd.DataFrame, is_ko_phase: bool = False) -> pd.DataFrame:
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
        df_xp = df_xp.sort_values(by="xP", ascending=False).head(5).reset_index(drop=True)
        return df_xp

    def calculate_pool_optimal_tips(self, score_matrix: pd.DataFrame, is_ko_phase: bool = False, aggressiveness: float = 0.0) -> pd.DataFrame:
        """
        Pool-Strategie: nicht den Erwartungswert maximieren, sondern den Vorsprung
        gegenüber dem Feld. In einem Tippspiel gewinnt das Maximum, nicht der Schnitt –
        wer immer den Favoriten-Tipp (Chalk) abgibt, kann sich vom Feld nicht absetzen.

        Modell: Das Feld tippt den xP-optimalen "Chalk"-Tipp. Für jeden Kandidaten-Tipp t
        ist die Vorsprungs-Zufallsvariable A = Punkte(t) - Punkte(Chalk) über die
        Resultatverteilung. Bewertet wird E[A] + λ·SD[A] mit λ = aggressiveness.
          - aggressiveness = 0  → reiner Chalk-Tipp (max xP), ideal in Führung / kleinem Pool.
          - aggressiveness > 0  → kontrarianische Tipps mit höherem Ceiling, ideal bei
            Rückstand / grossem Pool / K.o.-Phase (Punkte verdoppelt).
        Typische Werte: 0.3 (leicht offensiv) bis 1.0 (stark kontrarianisch).
        """
        max_tip_goals = 5

        # 1. Chalk-Tipp des Feldes bestimmen (xP-Maximum)
        chalk_home, chalk_away, best_xp = 0, 0, -1.0
        for t_home in range(max_tip_goals + 1):
            for t_away in range(max_tip_goals + 1):
                xp, _ = self._points_distribution(t_home, t_away, score_matrix, is_ko_phase)
                if xp > best_xp:
                    best_xp, chalk_home, chalk_away = xp, t_home, t_away

        # 2. Vorsprungsverteilung jedes Kandidaten gegen den Chalk-Tipp
        results = []
        for t_home in range(max_tip_goals + 1):
            for t_away in range(max_tip_goals + 1):
                mean_adv = 0.0
                mean_adv_sq = 0.0
                xp = 0.0
                for a_home_str in score_matrix.index:
                    for a_away_str in score_matrix.columns:
                        prob = score_matrix.loc[a_home_str, a_away_str]
                        if prob <= 0:
                            continue
                        a_home, a_away = int(a_home_str), int(a_away_str)
                        pts = self._tip_points(t_home, t_away, a_home, a_away, is_ko_phase)
                        chalk_pts = self._tip_points(chalk_home, chalk_away, a_home, a_away, is_ko_phase)
                        adv = pts - chalk_pts
                        mean_adv += adv * prob
                        mean_adv_sq += (adv ** 2) * prob
                        xp += pts * prob
                sd_adv = max(0.0, mean_adv_sq - mean_adv ** 2) ** 0.5
                score = mean_adv + aggressiveness * sd_adv
                results.append({
                    "Tipp": f"{t_home}:{t_away}",
                    "xP": xp,
                    "edge_vs_field": mean_adv,
                    "upside": sd_adv,
                    "score": score,
                })

        df = pd.DataFrame(results)
        df = df.sort_values(by="score", ascending=False).head(5).reset_index(drop=True)
        return df

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
