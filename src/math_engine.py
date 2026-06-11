import pandas as pd
import numpy as np
import scipy.optimize as optimize
import scipy.stats as stats

class MathEngine:
    """
    A mathematical engine for betting calculations.
    """

    def __init__(self, elo_csv_path: str, name_mapping: dict = None):
        # Laden der Elo-Daten als Klassen-Attribut
        self.elo_df = pd.read_csv(elo_csv_path)
        
        # Ein einfaches Dictionary für Namens-Mapping, falls die API andere Namen nutzt
        self.name_mapping = name_mapping or {}

    @staticmethod
    def remove_margin(odds_home: float, odds_draw: float, odds_away: float) -> dict[str, float]:
        """
        Calculates the true probabilities by removing the bookmaker's margin from decimal odds.
        
        Args:
            odds_home (float): Decimal odds for the home team to win.
            odds_draw (float): Decimal odds for a draw.
            odds_away (float): Decimal odds for the away team to win.
            
        Returns:
            dict[str, float]: A dictionary with the true probabilities for home, draw, and away.
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

    def get_elo_probability(self, rating_a: float, rating_b: float) -> float:
        """Berechnet die reine Elo-Siegwahrscheinlichkeit für Team A."""
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
            if home_norm not in self.elo_df['team_name'].values:
                raise ValueError(f"CRITICAL: Team '{home_norm}' fehlt in der elo_ratings.csv!")
            if away_norm not in self.elo_df['team_name'].values:
                raise ValueError(f"CRITICAL: Team '{away_norm}' fehlt in der elo_ratings.csv!")
            
            elo_home = self.elo_df.loc[self.elo_df['team_name'] == home_norm, 'elo_rating'].values[0]
            elo_away = self.elo_df.loc[self.elo_df['team_name'] == away_norm, 'elo_rating'].values[0] 
            
            # 3. Elo-Wahrscheinlichkeit berechnen
            prob_elo_home = self.get_elo_probability(elo_home, elo_away)
            
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
        
        Args:
            prob_home: Bookmaker implied probability for home win.
            prob_draw: Bookmaker implied probability for draw.
            prob_away: Bookmaker implied probability for away win.
            prob_over25: Bookmaker implied probability for over 2.5 goals.
            
        Returns:
            tuple[float, float]: Optimized (lambda_home, lambda_away) representing Expected Goals.
        """
        def cost_function(lambdas):
            l_home, l_away = lambdas
            
            # Matrix up to a reasonable max goals for calculating the match outcome probabilities
            max_goals = 10
            poisson_home = stats.poisson.pmf(np.arange(max_goals), l_home)
            poisson_away = stats.poisson.pmf(np.arange(max_goals), l_away)
            
            # Joint probability matrix
            prob_matrix = np.outer(poisson_home, poisson_away)
            
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
    def generate_exact_score_matrix(lambda_home: float, lambda_away: float, max_goals: int = 5) -> pd.DataFrame:
        """
        Generates a matrix of exact score probabilities using independent Poisson distributions.
        
        Args:
            lambda_home: Expected Goals for home team.
            lambda_away: Expected Goals for away team.
            max_goals: Maximum number of goals to compute probability for (default 5).
            
        Returns:
            pd.DataFrame: Matrix with rows as home goals and columns as away goals.
        """
        goals_range = np.arange(max_goals + 1)
        prob_home = stats.poisson.pmf(goals_range, lambda_home)
        prob_away = stats.poisson.pmf(goals_range, lambda_away)
        
        # Joint probability matrix
        prob_matrix = np.outer(prob_home, prob_away)
        
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
    def find_contrarian_value(score_matrix: pd.DataFrame) -> dict:
        """
        Finds the top 3 most probable exact scores from the score matrix.
        
        Args:
            score_matrix: DataFrame containing joint probabilities for exact scores.
            
        Returns:
            dict: Top 3 scorelines (e.g. '2-1') mapped to their probabilities.
        """
        # Flatten matrix into a Series with MultiIndex
        stacked = score_matrix.stack()
        # Create scoreline strings like "HomeGoals-AwayGoals"
        stacked.index = [f"{home}-{away}" for home, away in stacked.index]
        
        # Sort and get top 3 highest probabilities
        top_3 = stacked.sort_values(ascending=False).head(3)
        return top_3.to_dict()
