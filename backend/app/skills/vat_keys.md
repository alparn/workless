# BU-Schlüssel (Berichtigungsschlüssel) — DATEV Referenz

BU-Schlüssel (auch Steuerschlüssel genannt) steuern die automatische Umsatzsteuer-Verarbeitung in DATEV. Wird ein BU-Schlüssel bei einer Buchung angegeben, splittet DATEV automatisch den Bruttobetrag in Netto + USt.

## Schlüssel für Eingangsrechnungen (Vorsteuer)

| BU | Steuersatz | Verwendung | Beispiel |
|----|-----------|------------|---------|
| 8 | 7% VSt | Eingangsrechnungen mit 7% MwSt | Lebensmittel, Bücher, Zeitschriften, ÖPNV |
| 9 | 19% VSt | Eingangsrechnungen mit 19% MwSt | Standard-Eingangsrechnungen, Büromaterial, Dienstleistungen |

## Schlüssel für Ausgangsrechnungen (Umsatzsteuer)

| BU | Steuersatz | Verwendung | Beispiel |
|----|-----------|------------|---------|
| 2 | 7% USt | Ausgangsrechnungen mit 7% MwSt | Verkauf ermäßigter Waren |
| 3 | 19% USt | Ausgangsrechnungen mit 19% MwSt | Standard-Ausgangsrechnungen |

## Sonderschlüssel

| BU | Bedeutung | Verwendung |
|----|-----------|------------|
| 40 | Innergemeinschaftlicher Erwerb 19% | Waren aus EU-Ausland |
| 46 | Innergemeinschaftliche Lieferung | Steuerfreie Lieferung an EU-Unternehmen |
| 44 | Reverse Charge (§13b) | Leistung aus EU-Ausland |
| 91 | Steuerfrei (ohne VSt-Abzug) | Steuerbefreite Umsätze (z.B. Versicherungen) |
| 94 | Steuerfrei (mit VSt-Abzug) | Innergemeinschaftliche Lieferungen |

## Entscheidungshilfe

1. **Standard-Eingangsrechnung** (Büromaterial, IT, Dienstleister): BU-Schlüssel **9** (19%)
2. **Ermäßigte Eingangsrechnung** (Lebensmittel, Bücher, ÖPNV): BU-Schlüssel **8** (7%)
3. **Standard-Ausgangsrechnung**: BU-Schlüssel **3** (19%)
4. **Ermäßigte Ausgangsrechnung**: BU-Schlüssel **2** (7%)
5. **Steuerfreie Rechnung** (Kleinunternehmer, § 4 UStG): **Kein** BU-Schlüssel
6. **Innergemeinschaftlicher Erwerb**: BU-Schlüssel **40**
7. **Reverse Charge**: BU-Schlüssel **44**

## Wichtig

- Der BU-Schlüssel wird in DATEV an das **Gegenkonto** angehängt (z.B. Gegenkonto "70001" mit BU "9" → DATEV bucht automatisch 19% Vorsteuer).
- Beträge in der Buchungszeile sind IMMER **Bruttobeträge**. DATEV zerlegt automatisch in Netto + Steuer.
- Bei gemischten Steuersätzen auf einer Rechnung: Separate Buchungszeile pro Steuersatz.
