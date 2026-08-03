# WM 2026 Predictor – Post-Tournament Analysis

## 1. Einleitung & Zielsetzung
Dieses Projekt wurde als quantitatives Vorhersage- und Analyse-Tool für das **SRF Tippspiel** zur Fußball-Weltmeisterschaft 2026 entwickelt. Das primäre Ziel war nicht nur die Vorhersage des wahrscheinlichsten Ergebnisses, sondern die systematische Maximierung der *Expected Points (xP)* anhand des spezifischen Regelwerks des Tippspiels (10 Punkte für das exakte Resultat, 8 Punkte für die korrekte Tordifferenz, 5-6 Punkte für die Tendenz). 

Zusätzlich diente das Dashboard als "Build-a-Bot"-Sandbox, um verschiedene Tipp-Strategien (Markt-Quoten vs. Elo-Rating) zu vergleichen und systematische Fehleinschätzungen des Marktes aufzudecken ("Model Edge").

---

## 2. Methodik & Mathematisches Modell

Die Architektur des Modells kombinierte etablierte stochastische Verfahren mit echten Marktdaten:

*   **Odds-to-xG Extraction (L-BFGS-B):** Mithilfe des `scipy.optimize.minimize`-Solvers wurden die aggregierten Konsens-Quoten der Buchmacher (bereinigt um die Buchmachermarge) in *Expected Goals (xG)* für Heim- und Auswärtsteam übersetzt.
*   **Bivariate Poisson & Dixon-Coles:** Die berechneten xG-Werte wurden genutzt, um eine Wahrscheinlichkeitsmatrix ($10 \times 10$) aller möglichen Ergebnisse aufzubauen. Dabei kam die **Dixon-Coles-Korrektur ($\rho = -0.15$)** zum Einsatz, um die bei unabhängigen Poisson-Verteilungen typische Unterschätzung von niedrigen Ergebnissen (0:0, 1:0, 0:1, 1:1) auszugleichen.
*   **Elo-Integration (70/30 Blend):** Ein eigens berechnetes, dynamisches Elo-Rating für alle 48 Nationen (inklusive Heimvorteil für USA/CAN/MEX) wurde zu 30% mit den Buchmacherquoten gemischt, um Formschwankungen und systematische Fehlbewertungen im Wettmarkt auszugleichen.

---

## 3. Architektur & Tech-Stack

Das Projekt wurde als moderne, entkoppelte Full-Stack-Applikation umgesetzt:
*   **Backend (Python/FastAPI):** Sorgte für die mathematischen Berechnungen, das Caching (Dynamic TTL zur Schonung des API-Quotas) und die Integration externer Datenquellen (ESPN für Live-Ergebnisse, The Odds API für Buchmacher-Quoten).
*   **Datenhaltung (MongoDB):** Speicherung historischer Ergebnisse, dynamischer Elo-Ratings und der Performance-Metriken der verschiedenen Bot-Strategien.
*   **Frontend (React 19 / Vite / Tailwind):** Ein responsives, im Glassmorphism-Design gehaltenes Dashboard, welches komplexe Datenstrukturen (Wahrscheinlichkeits-Matrizen, Monte-Carlo-Simulationen) für den Endnutzer visuell aufbereitet hat.

---

## 4. Evaluation: "Model Edge" & House Bots

Ein zentrales Feature war die **Model Edge**-Analyse, welche Situationen aufdeckte, in denen das Elo-Modell den Buchmachern stark widersprach. Der Algorithmus konnte besonders in der Gruppenphase erhebliche "Edges" ausnutzen, bei denen der Markt große Favoriten systematisch überschätzte.

Die Performance des Algorithmus (xP-Optimiser) wurde permanent gegen vier fix programmierte "House Bots" getestet. Nach Abschluss aller 104 Spiele ergab sich folgendes interne Ranking:

1.  **Algorithmus (xP-Optimiser):** 694 Punkte (6.67 Pkt/Spiel)
2.  **Gambler (Top-10 Random):** 693 Punkte
3.  **Broker (Buchmacher-Konsens):** 665 Punkte
4.  **Professor (100% Elo):** 652 Punkte
5.  **X-Sniper (Nur Unentschieden):** 315 Punkte

Innerhalb der algorithmischen Strategien hat der auf *Expected Points (xP)* optimierte Ansatz sein technisches Ziel voll erfüllt: Er schlug den reinen Buchmacher-Markt ("Broker") um 29 Punkte und dominierte das reine Elo-Modell ("Professor") deutlich. 

### 4.2 Vergleich mit dem SRF-Tippspiel Leaderboard (Die Bonusfragen-Problematik)

Ein direkter Vergleich der algorithmischen Performance mit dem [offiziellen SRF-Leaderboard](https://wmtippspiel.srf.ch/ranking/players) ist extrem stark verzerrt (biased). Das SRF-Tippspiel vergab vor Turnierbeginn bis zu **130 Bonus-Punkte** für korrekt beantwortete Zusatzfragen (z.B. Weltmeister, Torschützenkönig, Finalisten). 

Da der entwickelte Algorithmus rein auf Basis von Einzelspiel-Wahrscheinlichkeiten agierte (Match-by-Match) und folglich **0 Bonus-Punkte** gesammelt hat, kämpfte er mit einem massiven künstlichen Handicap gegenüber den menschlichen Spielern. 

**Bereinigter Vergleich (Punkte aus Spielen):**
Zieht man die Bonus-Punkte der menschlichen Spitzengruppe ab, ergibt sich folgendes bereinigtes Ranking an der absoluten Weltspitze:
1.  **Sam Haab:** 822 Punkte (7.90 Pkt/Spiel)
2.  **Monika W:** 799 Punkte (7.68 Pkt/Spiel)
3.  **Dijana S:** 785 Punkte (7.54 Pkt/Spiel)
4.  **Andy S:** 778 Punkte (7.48 Pkt/Spiel)
...
*Der Algorithmus in der Gesamtwertung:*
X.  **Algorithmus (WM Predictor):** 694 Punkte (Top 15% global)

**Fazit & Ursachenforschung:** 
Obwohl der xP-Algorithmus nicht die absolute Weltspitze der menschlichen "Glückstipper" erreichen konnte, ist das Resultat ein gigantischer Erfolg: **Selbst mit dem brutalen Handicap von 0 Bonuspunkten landete der Algorithmus auf Platz 74.863 von ca. 500.000 Teilnehmern!** Damit gehört das reine, unvoreingenommene Mathematik-Modell zu den **besten 15% aller Spieler weltweit**.

Dass der Algorithmus die absolute Spitze (wie Sam Haab) nicht erreichte, lässt sich auf zwei methodische Faktoren zurückführen:
1. **Sample Size & "The Gambler's Fallacy":** Ein Turnier mit 104 Spielen ist statistisch gesehen eine sehr kleine Stichprobe. Während der Algorithmus strikt den "sicheren" stochastischen Erwartungswert spielt, nehmen menschliche Spieler eine viel höhere Varianz in Kauf. Bei einer halben Million Mitspielern gibt es rein statistisch immer Ausreißer, deren riskante Exakt-Tipps durch Glück perfekt eintreffen. Bemerkenswert: Auch der völlig zufällige "Gambler"-Bot hat mit 693 Punkten fast exakt so gut abgeschnitten wie der xP-Algorithmus!
2. **Die Natur des SRF-Regelwerks:** Das SRF-Tippspiel belohnt exakte Resultate extrem stark (10 Punkte). Modelle, die stochastische Verteilungen nutzen, tendieren dazu, die "sichersten" Durchschnittsresultate (wie 1:1 oder 1:0) zu tippen, weshalb sie seltener die vollen 10 Punkte für wilde 3:2 Ergebnisse kassieren, die von mutigen menschlichen Spielern vorhergesehen wurden.

---

## 5. Learnings & Fazit

> [!TIP]
> **Erkenntnisse aus dem Betrieb**
> *   **Cold-Starts bei Render:** Das Hosting auf dem Render Free-Tier führte zu spürbaren Verzögerungen beim ersten Aufruf ("Application loading"). Ein Ping-Endpunkt linderte das Problem, für einen echten Produktionsbetrieb wäre jedoch ein Upgrade nötig.
> *   **Expected Points vs. Wahrscheinlichkeit:** Die Optimierung auf xP nach SRF-Regeln führte oftmals zu anderen Tipps (z.B. eher "2:1" statt "1:0"), als es die reine Ergebniswahrscheinlichkeit vorgegeben hätte. Dies bestätigte die Grundthese des Projekts.
> *   **Dixon-Coles war entscheidend:** Ohne die Korrektur der niedrigen Resultate wäre die Trefferquote bei "knappen" Ergebnissen spürbar geringer ausgefallen.

Insgesamt hat das Projekt erfolgreich demonstriert, wie sich Echtzeit-Sportdaten, stochastische Mathematik und modernes Web-Engineering zu einer robusten Analyse-Plattform kombinieren lassen.
