import streamlit as st
import pandas as pd
import sys
import os

# Add the parent directory to sys.path to allow imports from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.odds_engine import OddsApiEngine
from src.math_engine import MathEngine

# Konstantes Dictionary für robustes Team-Mapping.
# Wird in Zukunft um weitere internationale Variationen erweitert.
TEAM_MAPPING = {
    "USA": "United States",
    "Korea Republic": "South Korea",
    "IR Iran": "Iran",
    "Czechia": "Czech Republic",
    "Côte d'Ivoire": "Ivory Coast"
}

# Set page config
st.set_page_config(layout="wide", page_title="🏆 WM 2026 Predictor")

@st.cache_data(ttl=3600)
def fetch_odds_data():
    """
    Fetches odds data from the API and caches the result.
    Fetching both h2h and totals markets to get Over/Under 2.5.
    """
    engine = OddsApiEngine()
    try:
        # In the Odds API, multiple markets can often be passed as comma-separated values
        data = engine.get_world_cup_odds(market="h2h,totals")
    except:
        # Fallback to h2h only if multiple markets fail
        data = engine.get_world_cup_odds(market="h2h")
    return data

@st.cache_data
def load_elo_data():
    """
    Lädt die Elo-Ratings aus der CSV-Datei oder erstellt ein kleines Fallback-DataFrame.
    """
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'elo_ratings.csv')
    try:
        return pd.read_csv(csv_path)
    except Exception:
        # Fallback Mock DataFrame
        return pd.DataFrame({
            "team_code": ["GER", "ARG", "FRA", "ESP", "USA"],
            "team_name": ["Deutschland", "Argentinien", "Frankreich", "Spanien", "United States"],
            "elo_rating": [1980, 2140, 2090, 2075, 1600]
        })

def extract_odds(match):
    """
    Hilfsfunktion, um Quoten aus der API-Payload zu extrahieren.
    """
    home_team = match.get("home_team")
    away_team = match.get("away_team")
    
    # Default/Mock Quoten, falls die API bestimmte Werte nicht liefert
    odds = {
        "home": 2.50,
        "draw": 3.20,
        "away": 2.80,
        "over25": 1.90,
        "under25": 1.90
    }
    
    # Versuche echte Quoten aus dem ersten Buchmacher zu extrahieren
    if "bookmakers" in match and len(match["bookmakers"]) > 0:
        bookie = match["bookmakers"][0]
        for market in bookie.get("markets", []):
            if market["key"] == "h2h":
                for outcome in market.get("outcomes", []):
                    if outcome["name"] == home_team:
                        odds["home"] = outcome["price"]
                    elif outcome["name"] == away_team:
                        odds["away"] = outcome["price"]
                    elif outcome["name"] == "Draw":
                        odds["draw"] = outcome["price"]
            elif market["key"] == "totals":
                for outcome in market.get("outcomes", []):
                    # Der Point bei Totals ist oft 2.5 für Over/Under
                    if outcome["name"] == "Over" and outcome.get("point", 2.5) == 2.5:
                        odds["over25"] = outcome["price"]
                    elif outcome["name"] == "Under" and outcome.get("point", 2.5) == 2.5:
                        odds["under25"] = outcome["price"]
    
    return odds

def main():
    st.title("🏆 WM 2026 Predictor - Edge Analytics")
    
    # 1. Daten laden
    elo_df = load_elo_data()
    elo_csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'elo_ratings.csv')
    
    # Initialisiere die MathEngine
    # (Wir erstellen im Zweifel ein Dummy-CSV, damit die Initialisierung nicht fehlschlägt,
    # falls elo_ratings.csv fehlt, aber in diesem Projekt ist es bereits angelegt).
    if not os.path.exists(elo_csv_path):
        os.makedirs(os.path.dirname(elo_csv_path), exist_ok=True)
        elo_df.to_csv(elo_csv_path, index=False)
        
    math_engine = MathEngine(elo_csv_path, TEAM_MAPPING)
    
    with st.spinner("Zapfe Buchmacher-Modelle an..."):
        try:
            api_matches = fetch_odds_data()
        except Exception as e:
            st.error(f"Fehler beim Abrufen der API-Daten: {e}")
            return
            
    if not api_matches or not isinstance(api_matches, list):
        st.warning("Keine aktuellen Spiele in der API gefunden oder das API-Limit wurde erreicht.")
        return

    # 2. Sidebar: Match Auswahl
    st.sidebar.header("Spieleinstellungen")
    
    # Erstelle eine Liste von Match-Strings
    match_options = {f"{m.get('home_team', 'Unbekannt')} vs {m.get('away_team', 'Unbekannt')}": m for m in api_matches}
    
    selected_match_str = st.sidebar.selectbox("Wähle ein Spiel:", list(match_options.keys()))
    
    if selected_match_str:
        match_data = match_options[selected_match_str]
        home_team = match_data.get("home_team", "Heimteam")
        away_team = match_data.get("away_team", "Auswärtsteam")
        
        st.header(f"⚽ {home_team} vs {away_team}")
        
        try:
            # Trigger Elo Validation
            math_engine.merge_odds_and_elo([match_data])
            
            # Step A: Probabilities extrahieren
            st.subheader("Schritt A: Rohdaten der Buchmacher")
            odds = extract_odds(match_data)
            
            # Umwandlung der Quoten in Wahrscheinlichkeiten
            prob_home = 1.0 / odds["home"]
            prob_draw = 1.0 / odds["draw"]
            prob_away = 1.0 / odds["away"]
            prob_over25 = 1.0 / odds["over25"]
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric(label=f"Sieg {home_team} (1)", value=odds["home"], delta=f"{prob_home:.1%} Wahrsch.")
            col2.metric(label="Unentschieden (X)", value=odds["draw"], delta=f"{prob_draw:.1%} Wahrsch.", delta_color="off")
            col3.metric(label=f"Sieg {away_team} (2)", value=odds["away"], delta=f"{prob_away:.1%} Wahrsch.")
            col4.metric(label="Über 2.5 Tore", value=odds["over25"], delta=f"{prob_over25:.1%} Wahrsch.")
            
            # Step B: xG Derivation
            st.subheader("Schritt B: Erwartete Tore (xG) berechnet")
            
            with st.spinner("Optimiere Poisson-Verteilung..."):
                xg_home, xg_away = math_engine.derive_xg_from_odds(
                    prob_home=prob_home,
                    prob_draw=prob_draw,
                    prob_away=prob_away,
                    prob_over25=prob_over25
                )
            
            col_xg1, col_xg2 = st.columns(2)
            col_xg1.metric(label=f"xG {home_team}", value=f"{xg_home:.2f}")
            col_xg2.metric(label=f"xG {away_team}", value=f"{xg_away:.2f}")
            
            # Step C: The Matrix
            st.subheader("Schritt C: Die Exakte Ergebnis-Matrix")
            st.markdown("Farbkodierte Heatmap der wahrscheinlichsten Endstände basierend auf den berechneten xG-Werten.")
            
            score_matrix = math_engine.generate_exact_score_matrix(xg_home, xg_away, max_goals=5)
            
            # Wende Pandas Styling für die Heatmap an
            styled_matrix = score_matrix.style.background_gradient(cmap='YlGnBu').format("{:.2%}")
            st.dataframe(styled_matrix, use_container_width=True)
            
            # Step D: The Edge
            st.subheader("Schritt D: Die Value-Empfehlungen")
            top_3_scores = math_engine.find_contrarian_value(score_matrix)
            
            st.success("🎯 **Top 3 Empfohlene Exakte Ergebnisse:**")
            
            # Ergebnisse hübsch formatieren
            for idx, (scoreline, prob) in enumerate(top_3_scores.items(), 1):
                st.info(f"**Platz {idx}:** Ergebnis **{scoreline}** mit einer Wahrscheinlichkeit von **{prob:.2%}**")
                
        except ValueError as ve:
            st.error(str(ve))
        except Exception as e:
            st.warning(f"Das mathematische Modell konnte für dieses Spiel nicht vollständig ausgeführt werden. Fehlerdetails: {e}")

if __name__ == "__main__":
    main()
