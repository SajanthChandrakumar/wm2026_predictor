import streamlit as st
import pandas as pd
import sys
import os
import matplotlib.colors as mcolors

# Add the parent directory to sys.path to allow imports from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.odds_engine import OddsApiEngine
from src.math_engine import MathEngine

TEAM_MAPPING = {
    "United States": "United States",
    "USA": "United States",
    "Korea Republic": "South Korea",
    "South Korea": "South Korea",
    "Czech Republic": "Czech Republic",
    "Czechia": "Czech Republic",
    "IR Iran": "Iran",
    "Côte d'Ivoire": "Ivory Coast",
    "Ivory Coast": "Ivory Coast",
    "Saudi Arabia": "Saudi Arabia",
    "KSA": "Saudi Arabia"
}

DISPLAY_MAPPING = {
    "United States": "🇺🇸 USA",
    "USA": "🇺🇸 USA",
    "South Korea": "🇰🇷 South Korea",
    "Korea Republic": "🇰🇷 South Korea",
    "Iran": "🇮🇷 Iran",
    "IR Iran": "🇮🇷 Iran",
    "Czech Republic": "🇨🇿 Czech Republic",
    "Czechia": "🇨🇿 Czech Republic",
    "Ivory Coast": "🇨🇮 Ivory Coast",
    "Côte d'Ivoire": "🇨🇮 Ivory Coast",
    "Argentina": "🇦🇷 Argentina",
    "France": "🇫🇷 France",
    "Germany": "🇩🇪 Germany",
    "Spain": "🇪🇸 Spain",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 England",
    "Brazil": "🇧🇷 Brazil",
    "Portugal": "🇵🇹 Portugal",
    "Netherlands": "🇳🇱 Netherlands",
    "Italy": "🇮🇹 Italy",
    "Belgium": "🇧🇪 Belgium",
}

# Set page config
st.set_page_config(layout="wide", page_title="WC PREDICTOR 2026", page_icon="🏆")

def inject_custom_css():
    st.markdown("""
    <style>
    /* Global Backgrounds */
    .stApp {
        background-color: #1A1D24;
    }
    
    /* Hide Streamlit Chrome */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #1A1D24 !important;
        border-right: 1px solid #333945;
    }
    
    /* Right Side Card Styling (Matches & Odds) */
    .odds-card {
        background-color: #232730;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #333945;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4);
        color: #E2E8F0;
        font-family: 'Inter', sans-serif;
    }
    
    .team-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 15px;
        font-size: 16px;
        font-weight: 500;
    }
    
    .odds-pill {
        background-color: #1A1D24;
        padding: 5px 12px;
        border-radius: 6px;
        border: 1px solid #333945;
        font-weight: bold;
        color: #FACC15;
    }
    
    /* Heatmap Table Reset */
    table {
        color: white !important;
        background-color: transparent !important;
        border-collapse: separate;
        border-spacing: 4px;
    }
    th {
        background-color: #1A1D24 !important;
        border: none !important;
        text-align: center !important;
        font-weight: 500 !important;
        color: #94A3B8 !important;
    }
    td {
        text-align: center !important;
        vertical-align: middle !important;
        border: 2px solid #1A1D24 !important;
        width: 60px !important;
        height: 60px !important;
        border-radius: 4px !important;
    }
    
    /* Custom Odds Card Styling */
    .odds-card {
        background-color: #232730;
        border-radius: 8px;
        padding: 15px;
        border: 1px solid #333945;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    .team-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
        font-weight: 600;
    }
    .odds-pill {
        background-color: #1A1D24;
        padding: 4px 12px;
        border-radius: 20px;
        color: #FACC15;
    }
    
    /* Metric Cards Override */
    div[data-testid="metric-container"] {
        background-color: #232730;
        border-radius: 8px;
        padding: 10px 15px;
        border: 1px solid #333945;
        border-left: 4px solid #FACC15;
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def fetch_odds_data():
    engine = OddsApiEngine()
    try:
        data = engine.get_world_cup_odds(market="h2h,totals")
    except:
        data = engine.get_world_cup_odds(market="h2h")
    return data

@st.cache_data
def load_elo_data():
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'elo_ratings.csv')
    try:
        return pd.read_csv(csv_path)
    except Exception:
        return pd.DataFrame({
            "team_code": ["GER", "ARG", "FRA"],
            "team_name": ["Deutschland", "Argentinien", "Frankreich"],
            "elo_rating": [1980, 2140, 2090]
        })

def extract_odds(match):
    home_team = match.get("home_team")
    away_team = match.get("away_team")
    odds = {}
    
    if "bookmakers" in match:
        for bookie in match["bookmakers"]:
            for market in bookie.get("markets", []):
                if market["key"] == "h2h":
                    for outcome in market.get("outcomes", []):
                        if outcome["name"] == home_team and "home" not in odds:
                            odds["home"] = outcome["price"]
                        elif outcome["name"] == away_team and "away" not in odds:
                            odds["away"] = outcome["price"]
                        elif outcome["name"] == "Draw" and "draw" not in odds:
                            odds["draw"] = outcome["price"]
                elif market["key"] == "totals":
                    for outcome in market.get("outcomes", []):
                        if outcome["name"] == "Over" and outcome.get("point", 2.5) == 2.5 and "over25" not in odds:
                            odds["over25"] = outcome["price"]
                        elif outcome["name"] == "Under" and outcome.get("point", 2.5) == 2.5 and "under25" not in odds:
                            odds["under25"] = outcome["price"]
                            
            # Wenn wir alle Quoten haben, können wir abbrechen
            if all(k in odds for k in ["home", "draw", "away", "over25"]):
                break
                
    # Fallback für Totals (over/under 2.5), falls diese fehlen, aber H2H da ist
    if all(k in odds for k in ["home", "draw", "away"]) and "over25" not in odds:
        odds["over25"] = 1.90
        odds["under25"] = 1.90
    
    required_keys = ["home", "draw", "away", "over25"]
    missing_keys = [k for k in required_keys if k not in odds]
    
    if missing_keys:
        raise ValueError("Keine Quoten für diesen Markt verfügbar")
    return odds

def main():
    inject_custom_css()
    
    # 1. Daten laden
    elo_df = load_elo_data()
    elo_csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'elo_ratings.csv')
    
    if not os.path.exists(elo_csv_path):
        os.makedirs(os.path.dirname(elo_csv_path), exist_ok=True)
        elo_df.to_csv(elo_csv_path, index=False)
        
    math_engine = MathEngine(elo_csv_path, TEAM_MAPPING)
    
    with st.spinner("Fetching Data API..."):
        try:
            api_matches = fetch_odds_data()
        except Exception as e:
            st.error(f"Fehler beim Abrufen der API-Daten: {e}")
            return
            
    if not api_matches or not isinstance(api_matches, list):
        st.warning("Keine aktuellen Spiele in der API gefunden.")
        return

    # 2. API Quota Tracker
    st.sidebar.markdown("### 📊 API Quota")
    quota_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'api_quota.json')
    try:
        import json
        if os.path.exists(quota_path):
            with open(quota_path, 'r', encoding='utf-8') as f:
                quota_data = json.load(f)
            st.sidebar.metric(
                label="API Requests Remaining", 
                value=quota_data.get('remaining', 'Unknown'), 
                delta=f"-{quota_data.get('used', 'Unknown')} used", 
                delta_color="inverse"
            )
        else:
            st.sidebar.info("Waiting for first request...")
    except Exception:
        pass
    st.sidebar.markdown("---")

    # 3. Sidebar Navigation (Fake)
    st.sidebar.markdown("### 🏆 WC PREDICTOR 2026")
    st.sidebar.markdown("---")
    st.sidebar.radio("Navigation", [
        "⊞ Dashboard", 
        "☑️ My Predictions", 
        "🏆 Tournament View", 
        "🧮 Heatmap Matrix", 
        "📄 Bet Slip", 
        "🏅 Rankings",
        "⚙️ Settings"
    ], index=3)
    
    st.sidebar.markdown("---")
    
    if st.sidebar.button("🔄 Elo-Ratings mit API synchronisieren"):
        processed_json_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed_matches.json')
        odds_engine = OddsApiEngine() 
        
        with st.spinner("Synchronisiere abgeschlossene Spiele..."):
            try:
                completed_matches = odds_engine.get_completed_scores(days_from=3)
                updates = math_engine.update_elo_from_api_scores(
                    api_scores=completed_matches, 
                    processed_matches_file=processed_json_path
                )
                
                if updates > 0:
                    math_engine.elo_df.to_csv(math_engine.elo_csv_path, index=False)
                    st.sidebar.success(f"Erfolgreich! {updates} neue Spiele verarbeitet und Elo aktualisiert.")
                else:
                    st.sidebar.info("Keine neuen, unverarbeiteten Spiele gefunden.")
            except Exception as e:
                st.sidebar.error(f"Fehler bei der Synchronisation: {e}")
                
    st.sidebar.markdown("---")
    
    # Header Area
    col_head1, col_head2, col_head3 = st.columns([3, 1, 1])
    with col_head1:
        st.markdown("### Turnier-Heatmap | Match Predictions")
    with col_head2:
        pass # Moved toggle to sidebar
    with col_head3:
        if st.button("🔄 Refresh Data"):
            fetch_odds_data.clear()
            st.rerun()
            
    st.markdown("---")
    
    match_options = {f"{m.get('home_team', 'Unbekannt')} vs {m.get('away_team', 'Unbekannt')}": m for m in api_matches}
    
    st.sidebar.markdown("### Spieleinstellungen")
    is_ko = st.sidebar.toggle("K.O.-Phase (Doppelte Punkte)")
    selected_match_str = st.sidebar.selectbox("Wähle ein Spiel:", list(match_options.keys()))
    
    if selected_match_str:
        match_data = match_options[selected_match_str]
        home_team_raw = match_data.get("home_team", "Heimteam")
        away_team_raw = match_data.get("away_team", "Auswärtsteam")
        
        home_team_disp = DISPLAY_MAPPING.get(home_team_raw, home_team_raw)
        away_team_disp = DISPLAY_MAPPING.get(away_team_raw, away_team_raw)
        
        try:
            math_engine.merge_odds_and_elo([match_data])
            odds = extract_odds(match_data)
            
            prob_home = 1.0 / odds["home"]
            prob_draw = 1.0 / odds["draw"]
            prob_away = 1.0 / odds["away"]
            prob_over25 = 1.0 / odds["over25"]
            
            xg_home, xg_away = math_engine.derive_xg_from_odds(
                prob_home=prob_home, prob_draw=prob_draw, prob_away=prob_away, prob_over25=prob_over25
            )
            
            if is_ko:
                xg_home *= 1.33
                xg_away *= 1.33
                
            score_matrix = math_engine.generate_exact_score_matrix(xg_home, xg_away, max_goals=5)
            xp_df = math_engine.calculate_expected_points(score_matrix, is_ko_phase=is_ko)
            
            # Layout Setup
            main_col, side_col = st.columns([2.5, 1])
            
            with main_col:
                st.markdown(f"### {home_team_disp} vs {away_team_disp}")
                
                # Mockup Colormap: Deep Blue -> Emerald Green -> Yellow
                colors = ['#1E293B', '#3B82F6', '#10B981', '#FACC15']
                cmap_custom = mcolors.LinearSegmentedColormap.from_list('mockup_cmap', colors)
                
                # Format to 1 decimal place to mimic the clean look, set max explicitly
                styled_matrix = score_matrix.style.background_gradient(
                    cmap=cmap_custom, vmin=0, vmax=score_matrix.values.max()
                ).format("{:.1%}")
                
                st.dataframe(styled_matrix, use_container_width=True, height=550)
                
            with side_col:
                st.markdown("### Matches & Odds")
                
                # Custom HTML Injection for the right card
                odds_html = f"""
                <div class="odds-card">
                    <div class="team-row">
                        <span>{home_team_disp}</span>
                        <span class="odds-pill">{odds['home']:.2f}</span>
                    </div>
                    <div class="team-row">
                        <span style="color: #94A3B8; font-size: 14px;">Draw</span>
                        <span class="odds-pill" style="color: #94A3B8;">{odds['draw']:.2f}</span>
                    </div>
                    <div class="team-row" style="margin-bottom: 0;">
                        <span>{away_team_disp}</span>
                        <span class="odds-pill">{odds['away']:.2f}</span>
                    </div>
                </div>
                """
                st.markdown(odds_html, unsafe_allow_html=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown("#### Value Predictions (xP)")
                if not xp_df.empty:
                    top_tip = xp_df.iloc[0]
                    st.success(f"🎯 **Top Pick: {top_tip['Tipp']}** ({top_tip['xP']:.1f} xP)")
                    
                    for i in range(1, min(4, len(xp_df))):
                        row = xp_df.iloc[i]
                        st.metric(label=f"Rank {i+1} | Score {row['Tipp']}", value=f"{row['xP']:.1f} xP")
                    
        except ValueError as ve:
            if "Keine Quoten für diesen Markt verfügbar" in str(ve):
                st.warning("Für dieses Spiel sind aktuell keine Quoten verfügbar.")
            else:
                st.error(str(ve))
        except Exception as e:
            st.warning(f"Fehler bei der Modellberechnung: {e}")

if __name__ == "__main__":
    main()
