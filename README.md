# WM 2026 Edge Predictor

Ein quantitatives Vorhersagemodell und Analytics-Dashboard für die Fußball-Weltmeisterschaft 2026. Dieses Projekt automatisiert die Suche nach Ineffizienzen ("Edge") in Sportwetten-Märkten und berechnet auf Basis komplexer Wahrscheinlichkeitsverteilungen den mathematisch optimalen Tipp für geschlossene Tippgruppen.

## Projektübersicht

Während klassische Tippspieler auf Intuition vertrauen, nutzt dieses System einen datengetriebenen Ansatz. Es zieht Live-Quoten von internationalen Buchmachern, bereinigt diese um die Buchmacher-Marge und leitet daraus über einen SciPy-Solver die erwarteten Tore (xG) ab. Diese Metriken werden mit einem dynamischen, sich selbst aktualisierenden Elo-Rating-System für alle 48 Teilnehmernationen abgeglichen, um Value-Bets und den maximalen Erwartungswert (Expected Points) zu identifizieren.

## Aktuelle Updates (12.06.2026)

* **Quantitative Blending & Roster Rotation:** Eine 70/30-Gewichtung verschmilzt die effizienten Live-Quoten der Buchmacher (70%) mit der internen Elo-Simulation (30%), um den wahren quantitativen Edge zu berechnen. Über dedizierte UI-Toggles lässt sich zudem eine Rotation am 3. Spieltag simulieren (-100 Elo-Strafe für B-Elf-Aufstellungen).
* **Dixon-Coles Adjustment ($\rho = -0.15$):** Eine fundamentale mathematische Korrektur der Poisson-Verteilung, die die Wahrscheinlichkeiten für typische Low-Scoring Draws (0:0, 1:0, 0:1, 1:1) künstlich anhebt, ohne den grundlegenden xG-Wert zu verzerren.
* **Host Nation Advantage:** Hartcodierter Heimvorteil (+80 Elo) für die Gastgeber USA, Kanada und Mexiko in der Vorhersage sowie in der rückwirkenden Elo-Punktvergabe.
* **Autarkic Background Cronjob:** Eine `apscheduler`-Integration triggert jeden Morgen um 04:00 Uhr vollautomatisch einen Background-Worker, der die neuesten Ergebnisse der *Odds API* fetcht, um das Elo-Rating in der Datenbank absolut autark aktuell zu halten.
* **Chronological Grid & Kick-Off Times:** Das Frontend parst die asynchronen ISO-Timestamps der API und serviert ein chronologisch sortiertes Grid mit lokalisierten (`de-DE`) Anstoßzeiten.

## Kern-Features

* **🔥 Automated Value Finder:** Das System berechnet im Hintergrund automatisch die xP-Matrizen für alle anstehenden Spiele und präsentiert dir in der "Top Value Bets"-Ansicht ein globales Ranking der absolut besten Tipps mit dem höchsten mathematischen Edge.
* **⚡ File-Based Production Cache:** Ein robustes, festplattenbasiertes Caching-System (`matches_cache.json`) speichert fertige API-Daten für eine Stunde. Das ermöglicht den fehlerfreien Betrieb über mehrere Server-Worker (z.B. Uvicorn/Gunicorn) in der Cloud, ohne jemals Rate-Limits bei *The Odds API* zu triggern.
* **Sleek Match Grid UI:** Ein modernes, kachelbasiertes Grid-System für die Spieleauswahl.
* **Reverse-Engineering von Expected Goals (xG):** Ein mathematischer Solver optimiert asymmetrische Poisson-Verteilungen gegen die Live-Quoten der Buchmacher (1X2 und Over/Under 2.5), um die exakten xG-Werte beider Teams zu extrahieren.
* **Poisson Score Matrix:** Generierung einer vollständigen Wahrscheinlichkeitsmatrix für alle exakten Spielergebnisse (von 0:0 bis 5:5).
* **Expected Points (xP) Calculator:** Eine spezialisierte Regel-Engine wendet das punktespezifische Regelwerk einer Tippgruppe auf die Poisson-Matrix an, um den Tipp mit der mathematisch höchsten Punkte-Erwartung zu berechnen ("Hedge-Betting").
* **Dynamische Elo-Kalibrierung:** Ein Idempotenz-gesicherter Backend-Service, der tägliche API-Spielergebnisse zieht und die Formkurve der Teams vollautomatisch anpasst. Fehlende Teams werden automatisch ergänzt (Base-Elo 1500).
* **Smart API Quota Management:** Integriertes Tracking der Rate-Limits durch das Auslesen versteckter HTTP-Response-Header.

## Tech-Stack

* **Backend & Logik:** Python 3.10+, FastAPI
* **Data Science & Mathematik:** Pandas, NumPy, SciPy (optimize, stats)
* **Frontend:** Vanilla HTML, CSS (Premium Dark Mode) und JavaScript (Fetch API)
* **Datenquellen:** The Odds API (REST)

## Die mathematische Pipeline

Die Vorhersage-Engine basiert nicht auf simplen Heuristiken, sondern auf einer mehrstufigen quantitativen Pipeline, die den aktuellen Branchenstandard der Sportdatenanalyse adaptiert:

1. **Datensammlung & Margen-Bereinigung:** Abruf von H2H- und Totals-Live-Quoten über die REST-API. Die impliziten Wahrscheinlichkeiten der Buchmacher werden algorithmisch vom "Vig" (Buchmacher-Marge) bereinigt, um die wahren Eintrittswahrscheinlichkeiten zu extrahieren.
2. **Dynamische Elo-Kalibrierung & Host Factor:** Die Grundstärke der Teams wird durch ein iteratives Elo-Rating-System abgebildet. Für die WM 2026 wendet das Modell einen systematischen *Host Nation Advantage* an: Nordamerikanische Gastgebernationen (USA, Kanada, Mexiko) erhalten vor der Wahrscheinlichkeitsberechnung einen dynamischen Boost von +80 Elo-Punkten, um den statistisch signifikanten Heimvorteil bei Weltmeisterschaften einzupreisen.
3. **Kostenfunktion & Solver (xG Extraction):** Ein Scipy.optimize Solver minimiert die Fehlerquote (Sum of Squared Errors) zwischen den echten Quoten-Wahrscheinlichkeiten und den theoretischen Ausgängen einer Poisson-Verteilung. Dadurch werden die Expected Goals ($\lambda$, $\mu$) für beide Teams isoliert.
4. **Dixon-Coles Korrektur:** Da unabhängige Poisson-Verteilungen die Häufigkeit von Low-Scoring-Draws im Fußball systematisch unterschätzen, interpoliert das Modell eine Dixon-Coles-Anpassung ($\rho = -0.15$). Dies korrigiert die Wahrscheinlichkeitsmatrix künstlich und kalibriert Ergebnisse wie 0:0 und 1:1 an die historische Realität des Fußballs.
5. **Expected Points (xP) Simulation:** Das System simuliert jeden theoretisch möglichen Tippvektor gegen die Dixon-Coles-Matrix und berechnet über das spezifische Regelwerk der Tippgruppe den maximalen Erwartungswert ("Hedge-Betting").

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
