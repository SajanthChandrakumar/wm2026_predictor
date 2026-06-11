# WM 2026 Edge Predictor

Ein quantitatives Vorhersagemodell und Analytics-Dashboard für die Fußball-Weltmeisterschaft 2026. Dieses Projekt automatisiert die Suche nach Ineffizienzen ("Edge") in Sportwetten-Märkten und berechnet auf Basis komplexer Wahrscheinlichkeitsverteilungen den mathematisch optimalen Tipp für geschlossene Tippgruppen.

## Projektübersicht

Während klassische Tippspieler auf Intuition vertrauen, nutzt dieses System einen datengetriebenen Ansatz. Es zieht Live-Quoten von internationalen Buchmachern, bereinigt diese um die Buchmacher-Marge und leitet daraus über einen SciPy-Solver die erwarteten Tore (xG) ab. Diese Metriken werden mit einem dynamischen, sich selbst aktualisierenden Elo-Rating-System für alle 48 Teilnehmernationen abgeglichen, um Value-Bets und den maximalen Erwartungswert (Expected Points) zu identifizieren.

## Kern-Features

* **🔥 Automated Value Finder:** Das System berechnet im Hintergrund automatisch die xP-Matrizen für alle anstehenden Spiele und präsentiert dir in der "Top Value Bets"-Ansicht ein globales Ranking der absolut besten Tipps mit dem höchsten mathematischen Edge.
* **⚡ File-Based Production Cache:** Ein robustes, festplattenbasiertes Caching-System (`matches_cache.json`) speichert fertige API-Daten für eine Stunde. Das ermöglicht den fehlerfreien Betrieb über mehrere Server-Worker (z.B. Uvicorn/Gunicorn) in der Cloud, ohne jemals Rate-Limits bei *The Odds API* zu triggern.
* **Sleek Match Grid UI:** Ein modernes, kachelbasiertes Grid-System für die Spieleauswahl anstelle von altbackenen Dropdown-Menüs.
* **Reverse-Engineering von Expected Goals (xG):** Ein mathematischer Solver optimiert asymmetrische Poisson-Verteilungen gegen die Live-Quoten der Buchmacher (1X2 und Over/Under 2.5), um die exakten xG-Werte beider Teams zu extrahieren.
* **Poisson Score Matrix:** Generierung einer vollständigen Wahrscheinlichkeitsmatrix für alle exakten Spielergebnisse (von 0:0 bis 5:5).
* **Expected Points (xP) Calculator:** Eine spezialisierte Regel-Engine, die das punktespezifische Regelwerk einer Tippgruppe (Tendenz, Tordifferenz, Exaktes Ergebnis) auf die Poisson-Matrix anwendet, um den Tipp mit der mathematisch höchsten Punkte-Erwartung zu berechnen ("Hedge-Betting").
* **Dynamische Elo-Kalibrierung:** Ein Idempotenz-gesicherter Backend-Service, der tägliche API-Spielergebnisse zieht und die Formkurve der Teams über die offizielle Elo-Formel (inkl. Margin-of-Victory Multiplikator) vollautomatisch anpasst. Fehlende Teams werden automatisch ergänzt (Base-Elo 1500).
* **Smart API Quota Management:** Integriertes Tracking der Rate-Limits durch das Auslesen versteckter HTTP-Response-Header.

## Tech-Stack

* **Backend & Logik:** Python 3.10+, FastAPI
* **Data Science & Mathematik:** Pandas, NumPy, SciPy (optimize, stats)
* **Frontend:** Vanilla HTML, CSS (Premium Dark Mode) und JavaScript (Fetch API)
* **Datenquellen:** The Odds API (REST)

## Die mathematische Pipeline

1. **Datensammlung:** Abruf der H2H- und Totals-Quoten über die REST-API.
2. **Margen-Bereinigung:** Herausrechnen des "Vig" (Buchmacher-Vorteil), um die echten (impliziten) Wahrscheinlichkeiten zu erhalten.
3. **Kostenfunktion & Solver:** Scipy.optimize minimiert die Fehlerquote zwischen den echten Wahrscheinlichkeiten und den theoretischen Ausgängen einer Poisson-Verteilung, um Lambda (xG) für Team A und B zu bestimmen.
4. **xP-Simulation:** Das Skript simuliert jeden theoretisch möglichen Tipp gegen die Wahrscheinlichkeitsmatrix und summiert die Erwartungswerte basierend auf der Punktevergabe der Tippgruppe.
5. **K.O.-Phasen-Anpassung:** Dynamische Skalierung der Expected Goals um den Faktor 1.33 bei Entscheidungsspielen, um die statistische Wahrscheinlichkeit von Toren in einer 120-minütigen Verlängerung korrekt einzupreisen.

## Installation & Setup

1. **Repository klonen und in das Verzeichnis wechseln:**
```bash
git clone https://github.com/SajanthChandrakumar/wm2026_predictor.git
cd wm2026_predictor
```

2. **Virtuelle Umgebung erstellen und Abhängigkeiten installieren:**
```bash
python3 -m venv .venv
source .venv/bin/activate  # Auf Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install fastapi "uvicorn[standard]"
```

3. **Umgebungsvariablen konfigurieren:**
Erstelle eine Datei namens `.env` im Hauptverzeichnis des Projekts und trage deinen API-Schlüssel ein:
```env
ODDS_API_KEY=dein_api_schluessel_hier
```

4. **Web-App starten:**
```bash
uvicorn src.api:app --reload
```
Öffne anschließend den Browser unter **http://127.0.0.1:8000/**, um das Dashboard zu laden.

## Operations & Wartung während des Turniers

Das System ist so konzipiert, dass es während des Turniers mit den realen Leistungen der Teams mitwächst.

Um das Elo-Rating aktuell zu halten, muss im Dashboard mindestens alle drei Tage der Button "Sync Elo (API)" gedrückt werden. Das System fragt daraufhin die beendeten Spiele der letzten 72 Stunden ab. Eine Idempotenz-Prüfung (`processed_matches.json`) garantiert, dass jedes Spiel strikt nur einmal in die mathematische Bewertung einfließt, selbst bei mehrfacher Synchronisation.
