import json
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.math_engine import MathEngine

def get_pts(tip_str, actual_str, is_ko):
    if not tip_str or tip_str == "N/A": return 0
    t_h, t_a = map(int, tip_str.split(':'))
    a_h, a_a = map(int, actual_str.split(':'))
    
    pts = 0
    t_diff = t_h - t_a
    a_diff = a_h - a_a
    
    if (t_diff > 0 and a_diff > 0) or (t_diff == 0 and a_diff == 0) or (t_diff < 0 and a_diff < 0):
        pts += 5
        if t_h == a_h: pts += 1
        if t_a == a_a: pts += 1
        if t_diff == a_diff: pts += 3
        
    return pts * 2 if is_ko else pts

def patch_history():
    archive_path = os.path.join(os.path.dirname(__file__), 'data', 'prediction_archive.json')
    elo_csv_path = os.path.join(os.path.dirname(__file__), 'data', 'elo_ratings.csv')
    
    math_engine = MathEngine(elo_csv_path, {})
    
    with open(archive_path, 'r') as f:
        archive = json.load(f)
        
    for match_id, match in archive.items():
        print(f"Patching {match_id}...")
        
        metadata = match.get("metadata", {})
        home_team = metadata.get("home_team")
        away_team = metadata.get("away_team")
        is_ko = metadata.get("is_ko_phase", False)
        
        pre = match.get("pre_match_snapshot") or {}
        odds = pre.get("odds")
        elo_state = pre.get("elo_state", {})
        
        if not odds:
            # It's a reconstructed match
            new_bots = math_engine.reconstruct_bot_tips(
                home_team=home_team,
                away_team=away_team,
                match_id=match_id,
                is_ko=is_ko
            )
            if new_bots:
                match["prediction"]["bots"] = new_bots
                if "post_match_result" in match and match["post_match_result"]["status"] == "completed":
                    actual_score = match["post_match_result"]["actual_score"]
                    bot_points = {}
                    for bot_name, bot_data in new_bots.items():
                        tip = bot_data.get("tip")
                        bot_points[bot_name] = get_pts(tip, actual_score, is_ko)
                    match["post_match_result"]["bot_points"] = bot_points
            continue
            
        b_prob_home = 1.0 / odds["home"]
        b_prob_draw = 1.0 / odds["draw"]
        b_prob_away = 1.0 / odds["away"]
        prob_over25 = 1.0 / odds["over25"] if "over25" in odds else None
        
        total_b = b_prob_home + b_prob_draw + b_prob_away
        true_probs = {
            "home": b_prob_home / total_b,
            "draw": b_prob_draw / total_b,
            "away": b_prob_away / total_b
        }
        
        elo_home = elo_state.get("home_rating", 1500)
        elo_away = elo_state.get("away_rating", 1500)
        
        elo_prob_home = 1 / (10 ** (-(elo_home - elo_away) / 400) + 1)
        elo_prob_away = 1.0 - elo_prob_home
        
        blend_home = (b_prob_home * 0.7) + (elo_prob_home * 0.3)
        blend_away = (b_prob_away * 0.7) + (elo_prob_away * 0.3)
        total_blend = blend_home + blend_away + b_prob_draw
        
        prob_home = blend_home / total_blend
        prob_away = blend_away / total_blend
        prob_draw = b_prob_draw / total_blend
        
        xg_h, xg_a = math_engine.derive_xg_from_odds(prob_home, prob_draw, prob_away, prob_over25)
        
        if is_ko:
            base_matrix = math_engine.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
            p_draw_90 = float(base_matrix.values.diagonal().sum())
            et_factor = 1 + p_draw_90 / 3
            xg_h *= et_factor
            xg_a *= et_factor
            
        sm = math_engine.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
        base_xp_df = math_engine.calculate_expected_points(sm, is_ko_phase=is_ko)
        
        # Override the MathEngine Elo state temporarily for 'The Professor' bot to use the historical Elo
        # rather than the current Elo!
        original_df = math_engine.elo_df.copy()
        if home_team in math_engine.elo_df['team_name'].values:
            math_engine.elo_df.loc[math_engine.elo_df['team_name'] == home_team, 'elo_rating'] = elo_home
        else:
            math_engine.elo_df.loc[len(math_engine.elo_df)] = ['XYZ', home_team, elo_home]
            
        if away_team in math_engine.elo_df['team_name'].values:
            math_engine.elo_df.loc[math_engine.elo_df['team_name'] == away_team, 'elo_rating'] = elo_away
        else:
            math_engine.elo_df.loc[len(math_engine.elo_df)] = ['XYZ', away_team, elo_away]

        bots = math_engine.compute_bot_tips(
            score_matrix=sm,
            base_xp_df=base_xp_df,
            true_probs=true_probs,
            prob_over25=prob_over25,
            home_team=home_team,
            away_team=away_team,
            match_id=match_id,
            is_ko_phase=is_ko
        )
        
        math_engine.elo_df = original_df # Restore original current Elo
        
        match["prediction"]["bots"] = bots
        
        if "post_match_result" in match and match["post_match_result"]["status"] == "completed":
            actual_score = match["post_match_result"]["actual_score"]
            bot_points = {}
            for bot_name, bot_data in bots.items():
                tip = bot_data.get("tip")
                bot_points[bot_name] = get_pts(tip, actual_score, is_ko)
            match["post_match_result"]["bot_points"] = bot_points

    with open(archive_path, 'w') as f:
        json.dump(archive, f, indent=4)
        
    print("Done patching history!")

if __name__ == "__main__":
    patch_history()
