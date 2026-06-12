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

    def merge_odds_and_elo(self, api_matches: list) -> pd.DataFrame:
        """
        Nimmt die JSON-Payload der API, extrahiert die Quoten,
        rechnet die Marge raus und merget die Elo-Ratings dazu.
        """
        processed_matches = []
        
        for match in api_matches:
            home_team = match.get("home_team", "")
            away_team = match.get("away_team", "")
            
            # 1. Namen normalisieren
            home_norm = self.name_mapping.get(home_team, home_team)
            away_norm = self.name_mapping.get(away_team, away_team)
            
            # 2. Elo-Ratings aus dem Dataframe extrahieren
            for team in [home_norm, away_norm]:
                if team not in self.elo_df['team_name'].values:
                    new_row = pd.DataFrame([{"team_code": team[:3].upper(), "team_name": team, "elo_rating": 1500}])
                    self.elo_df = pd.concat([self.elo_df, new_row], ignore_index=True)
                    self.elo_df.to_csv(self.elo_csv_path, index=False)
            
            elo_home = self.elo_df.loc[self.elo_df['team_name'] == home_norm, 'elo_rating'].values[0]
            elo_away = self.elo_df.loc[self.elo_df['team_name'] == away_norm, 'elo_rating'].values[0] 
            
            hosts = ["United States", "Canada", "Mexico"]
            is_home_host = home_norm in hosts
            is_away_host = away_norm in hosts
            
            # 3. Elo-Wahrscheinlichkeit berechnen
            prob_elo_home = self.get_elo_probability(elo_home, elo_away, is_a_host=is_home_host, is_b_host=is_away_host)
            
            # Hier kommt später die Extraktion der Buchmacher-Quoten hin...
            # Aus Gründen der Übersichtlichkeit stark verkürzt:
            true_odds_home = 0.50 # Beispielwert nach Margenbereinigung
            
            processed_matches.append({
                "match": f"{home_team} vs {away_team}",
                "elo_prob_home": prob_elo_home,
                "bookie_prob_home": true_odds_home,
                "edge_home": prob_elo_home - true_odds_home # Die mathematische Diskrepanz
            })
            
        return pd.DataFrame(processed_matches)

    @staticmethod
    def derive_xg_from_odds(prob_home: float, prob_draw: float, prob_away: float, prob_over25: float) -> tuple[float, float]:
        """
        Derives Expected Goals (xG) for home and away teams by minimizing the difference
        between bookmaker probabilities and Poisson-derived probabilities.
        """
        def cost_function(lambdas):
            l_home, l_away = lambdas
            
            # Matrix up to a reasonable max goals for calculating the match outcome probabilities
            max_goals = 10
            poisson_home = stats.poisson.pmf(np.arange(max_goals), l_home)
            poisson_away = stats.poisson.pmf(np.arange(max_goals), l_away)
            
            # Joint probability matrix
            prob_matrix = np.outer(poisson_home, poisson_away)
            
            # Dixon-Coles adjustment for low-scoring matches
            rho = -0.15
            tau_00 = 1 - (l_home * l_away * rho)
            tau_10 = 1 + (l_home * rho)
            tau_01 = 1 + (l_away * rho)
            tau_11 = 1 - rho
            
            prob_matrix[0, 0] *= tau_00
            prob_matrix[1, 0] *= tau_10
            prob_matrix[0, 1] *= tau_01
            prob_matrix[1, 1] *= tau_11
            
            # Normalize matrix after Dixon-Coles adjustment
            prob_matrix = prob_matrix / np.sum(prob_matrix)
            
            # Sum probabilities for outcomes
            calc_home = np.sum(np.tril(prob_matrix, -1))
            calc_draw = np.sum(np.diag(prob_matrix))
            calc_away = np.sum(np.triu(prob_matrix, 1))
            
            # Calculate over 2.5 probability
            goals_home_idx, goals_away_idx = np.indices((max_goals, max_goals))
            total_goals = goals_home_idx + goals_away_idx
            calc_over25 = np.sum(prob_matrix[total_goals > 2.5])
            
            # Cost function: Sum of squared errors
            error = (
                (calc_home - prob_home) ** 2 +
                (calc_draw - prob_draw) ** 2 +
                (calc_away - prob_away) ** 2 +
                (calc_over25 - prob_over25) ** 2
            )
            return error

        # Initial guess and bounds to prevent solver failure
        initial_guess = [1.5, 1.5]
        bounds = ((0.1, 5.0), (0.1, 5.0))
        
        result = optimize.minimize(cost_function, initial_guess, bounds=bounds)
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

    def calculate_expected_points(self, score_matrix: pd.DataFrame, is_ko_phase: bool = False) -> pd.DataFrame:
        """
        Calculates the Expected Points (xP) for tips from 0:0 up to 5:5 based on the specific ruleset.
        """
        def calc_points(tipped_home: int, tipped_away: int, actual_home: int, actual_away: int) -> int:
            points = 0
            
            # Tendency
            tipped_tendency = np.sign(tipped_home - tipped_away)
            actual_tendency = np.sign(actual_home - actual_away)
            tendency_correct = tipped_tendency == actual_tendency
            
            if tendency_correct:
                points += 5
                
            # Exact goals
            if tipped_home == actual_home:
                points += 1
            if tipped_away == actual_away:
                points += 1
                
            # Goal difference
            if tendency_correct and (tipped_home - tipped_away) == (actual_home - actual_away):
                points += 3
                
            return points * 2 if is_ko_phase else points

        results = []
        max_tip_goals = 5
        
        # Iterating over all possible tips
        for t_home in range(max_tip_goals + 1):
            for t_away in range(max_tip_goals + 1):
                xp = 0.0
                
                # Iterating over the probability matrix
                for a_home_str in score_matrix.index:
                    for a_away_str in score_matrix.columns:
                        a_home = int(a_home_str)
                        a_away = int(a_away_str)
                        prob = score_matrix.loc[a_home_str, a_away_str]
                        
                        if prob > 0:
                            pts = calc_points(t_home, t_away, a_home, a_away)
                            xp += pts * prob
                            
                results.append({
                    "Tipp": f"{t_home}:{t_away}",
                    "xP": xp
                })
                
        df_xp = pd.DataFrame(results)
        df_xp = df_xp.sort_values(by="xP", ascending=False).head(5).reset_index(drop=True)
        return df_xp

    def _calculate_new_elo(self, rating_a: float, rating_b: float, actual_result_a: float, k_factor: int = 40, is_a_host: bool = False, is_b_host: bool = False) -> tuple[float, float]:
        """ Helper for standard Elo calculation """
        expected_a = self.get_elo_probability(rating_a, rating_b, is_a_host=is_a_host, is_b_host=is_b_host)
        expected_b = 1 - expected_a
        
        new_rating_a = rating_a + k_factor * (actual_result_a - expected_a)
        new_rating_b = rating_b + k_factor * ((1 - actual_result_a) - expected_b)
        return new_rating_a, new_rating_b

    def update_elo_from_api_scores(self, api_scores: list, processed_matches_file: str = 'data/processed_matches.json') -> int:
        """
        Updates Elo ratings based on completed matches from the API, 
        ensuring idempotency by tracking processed match IDs.
        """
        import os
        import json
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
                    
                new_elo_home, new_elo_away = self._calculate_new_elo(
                    elo_home, elo_away, result_home, 
                    is_a_host=is_home_host, is_b_host=is_away_host
                )
                
                self.elo_df.loc[self.elo_df['team_name'] == home_norm, 'elo_rating'] = new_elo_home
                self.elo_df.loc[self.elo_df['team_name'] == away_norm, 'elo_rating'] = new_elo_away
                
                processed_set.add(match_id)
                processed_ids.append(match_id)
                updates_made += 1
                
        if updates_made > 0:
            os.makedirs(os.path.dirname(os.path.abspath(processed_matches_file)), exist_ok=True)
            with open(processed_matches_file, 'w', encoding='utf-8') as f:
                json.dump(processed_ids, f, indent=4)
                
        return updates_made
