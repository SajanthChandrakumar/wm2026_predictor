# Automatische Match-Hinweise

## Ziel

Jeder Modell-Tipp soll ohne Fachwissen verständlich werden. Direkt unter dem Tipp erklärt ein kurzer Hinweis, wer favorisiert ist, wie sicher die Aussage ist und welche vorhandenen Daten dafür sprechen. Der Hinweis erklärt das bestehende Modell; er berechnet keinen neuen Tipp und verändert keine Zahlen.

## Produktentscheidung

Version 1 verwendet keine externe KI oder LLM-API. Eine deterministische, lokal ausgeführte Hinweisfunktion formuliert ausschließlich aus bereits vorhandenen Match-Daten. Das ist kostenlos, sofort verfügbar, vollständig testbar und verhindert erfundene Gründe. Eine spätere KI darf höchstens denselben strukturierten Inhalt umformulieren; Tipp, Zahlen, Sicherheit und Quellen bleiben dann unveränderliche Eingaben.

## Datenvertrag

Eine reine Funktion `buildMatchHint(match: Match): MatchHint` lebt in `frontend-v2/src/lib/matchHint.ts` und wird von Dashboard und Spieldetail verwendet.

```ts
export type MatchHintConfidence = 'high' | 'medium' | 'low' | 'unavailable'
export type MatchHintSource = 'bookmaker' | 'elo' | 'unavailable'

export interface MatchHint {
  available: boolean
  summary: string
  confidence: MatchHintConfidence
  confidenceLabel: 'Hoch' | 'Mittel' | 'Niedrig' | 'Nicht verfügbar'
  source: MatchHintSource
  sourceLabel: 'Buchmacherquote' | 'Elo-Modellquote · nicht wettbar' | 'Nicht verfügbar'
  reasons: string[]
}
```

Die Funktion führt keine Requests aus, liest keinen globalen Zustand und mutiert das Match nicht.

## Quellenwahl

1. Sind `odds.home`, `odds.draw` und `odds.away` endliche Dezimalquoten größer als 1, werden daraus margenneutrale 1/X/2-Wahrscheinlichkeiten berechnet. Quelle ist `Buchmacherquote`.
2. Andernfalls dürfen `match.probabilities` nur bei `source_mode === 'elo-only'` verwendet werden. Quelle ist `Elo-Modellquote · nicht wettbar`.
3. Fehlen beide Grundlagen oder ist ihre Summe nicht positiv, ist der Hinweis nicht verfügbar.

Elo-Werte werden niemals als Buchmacherquoten bezeichnet. Fehlende Werte werden nicht geschätzt oder durch Standardwerte ersetzt.

## Favorit und Sicherheit

Die drei 1/X/2-Wahrscheinlichkeiten werden absteigend sortiert. `top` ist die höchste Wahrscheinlichkeit, `gap` ihr Abstand zur zweithöchsten.

- `high`: `top >= 0.55` und `gap >= 0.15`
- `medium`: `top >= 0.43` und `gap >= 0.08`
- `low`: alle übrigen verfügbaren Fälle
- `unavailable`: keine belastbare Wahrscheinlichkeitsquelle

Formulierungen:

- Hohe Sicherheit: `<Team> ist klarer Favorit.`
- Mittlere Sicherheit: `<Team> ist leichter Favorit.`
- Niedrige Sicherheit: `Das Spiel ist sehr ausgeglichen.`
- Ist Remis der wahrscheinlichste Ausgang, lautet der Einstieg unabhängig vom Schwellenwert: `Ein Unentschieden ist der wahrscheinlichste einzelne Ausgang.`
- Nicht verfügbar: `Für eine verständliche Erklärung fehlen derzeit ausreichende Daten.`

„Sicherheit“ bezeichnet ausschließlich die Eindeutigkeit zwischen den drei verfügbaren Ausgängen. Sie ist keine Gewinnzusage.

Die sichtbare Zusammenfassung besteht immer aus dem passenden Einstieg. Bei einem Heim- oder Auswärtsfavoriten mit `high` oder `medium` wird der erste verfügbare Grund als zweiter Satz angefügt. Bei `low`, Remis als wahrscheinlichstem Ausgang oder `unavailable` bleibt es beim Einstieg, damit keine widersprüchliche Sicherheit suggeriert wird. Die Zusammenfassung hat dadurch höchstens zwei Sätze.

## Begründungen

Es werden höchstens zwei belegbare Gründe ausgegeben. Gründe werden in dieser Reihenfolge gewählt und nur verwendet, wenn die Bedingung erfüllt ist:

1. **Expected Goals:** `xg_home` und `xg_away` sind endlich und unterscheiden sich um mindestens `0.35`. Der Vorteil muss zum favorisierten Team passen. Text mit gerundeten Werten: `Torerwartung: Bayern 1.84 zu Arsenal 1.22.`
2. **Aktuelle Form:** Genau das favorisierte Team besitzt `on_fire === true`. Text: `Bayern kommt mit der stärkeren aktuellen Form.`
3. **Club-Elo:** `elo_home_share` ist endlich, weicht mindestens `0.10` von `0.50` ab und stimmt mit dem favorisierten Heim- oder Auswärtsteam überein. Text mit Prozentwert: `Club-Elo sieht Bayern bei 64 % im direkten Stärkevergleich.`
4. **Gemeldete Ausfälle:** Die Gegenseite hat mindestens zwei mehr als fehlend gemeldete Spieler als das favorisierte Team. Text ohne medizinische Interpretation: `Beim Gegner sind mehr fehlende Spieler gemeldet.`
5. **K.-o.-Kontext:** `is_ko_phase` ist wahr und ein `first_leg_score` existiert. Dieser neutrale Risikohinweis darf als zweiter Grund erscheinen: `Das Hinspielergebnis kann den Spielverlauf stärker beeinflussen.`

Wenn kein Zusatzgrund die Schwelle erreicht, bleibt die Zusammenfassung bei der Favoriten- beziehungsweise Ausgeglichenheits-Aussage. Ein fehlender Grund wird niemals durch eine Vermutung ersetzt.
Teambezogene Gründe 1 bis 4 werden bei Remis als wahrscheinlichstem Ausgang nicht erzeugt. Der neutrale K.-o.-Kontext darf weiterhin erscheinen.

## UI

### Mobile Dashboard

Der bestehende Bereich „Unser Tipp“ erhält:

- eine kompakte Sicherheitsplakette `Hoch`, `Mittel` oder `Niedrig`;
- die maximal zweisätzige Zusammenfassung;
- die bestehende, unveränderte Quellenangabe;
- ein natives `<details>` mit der Beschriftung `Warum?`, wenn mindestens ein Grund vorhanden ist.

Das native Element bietet Tastaturbedienung ohne zusätzlichen JavaScript-Zustand. Die Gründe erscheinen als kurze Liste. Bei `unavailable` wird keine Sicherheitsfarbe und kein leeres „Warum?“ angezeigt.

### Spieldetail

Oberhalb der quantitativen Analyse erscheint dieselbe Zusammenfassung in einer einfachen Karte. Das aufgeklappte „Warum?“ zeigt dieselben Gründe wie das Dashboard. Dadurch widersprechen sich Startseite und Detailansicht nicht.

### Darstellung

- `high`: zurückhaltendes Grün
- `medium`: Kobaltblau
- `low`: Orange
- keine rote Gefahrenfarbe, weil niedrige Sicherheit kein Fehler ist
- Text bleibt mindestens 16 px groß; `Warum?` besitzt ein mindestens 44 px hohes Ziel

## Fehler- und Sonderfälle

- Bei fehlenden Wahrscheinlichkeiten wird explizit der nicht verfügbare Text gezeigt.
- Bei ungültigen Quoten wird auf echte `elo-only`-Wahrscheinlichkeiten zurückgegriffen, niemals auf erfundene Quoten.
- Bei gespielten Matches erklärt der Hinweis weiterhin den damaligen Modell-Tipp; der Endstand wird nicht als Begründung verwendet.
- Unterschiedliche oder teilweise fehlende Form-, xG-, Elo-, Ausfall- und K.-o.-Daten reduzieren lediglich die Zahl der Gründe.
- Teamnamen verwenden `home_disp`/`away_disp` ohne vorangestellte Flagge, sonst den Rohteamnamen.

## Umfang

Geändert werden nur die neue reine Hinweisfunktion, ihre Tests, das mobile Dashboard, die Spieldetailansicht und das gebaute `frontend-v2/dist`. Backend, API-Antworten, Datenbank, Modellberechnung, Tipps und Quoten bleiben unverändert. Es werden keine Abhängigkeiten hinzugefügt.

## Tests und Abnahme

- Unit-Tests decken Buchmacher-, Elo-only-, unavailable-, hohe, mittlere und niedrige Sicherheit sowie Remis als Favorit ab.
- Unit-Tests decken xG-, Form-, Elo-, Ausfall- und K.-o.-Gründe sowie die Begrenzung auf zwei Gründe ab.
- Ein Integrationstest auf Quelltextebene sichert die Verwendung derselben Funktion in Dashboard und Detailansicht sowie das native `Warum?`-Element.
- Frontend: vollständige Node-Tests, Typecheck, Build und Lint.
- Backend: bestehende Tests bleiben unverändert grün.
- Browser bei 390 px: Zusammenfassung, Sicherheitsplakette, Quelle und aufklappbares `Warum?` mit echten UCL-Daten; keine horizontale Überbreite und keine Konsolenfehler.
