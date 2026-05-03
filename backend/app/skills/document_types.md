# Dokumenttyp-Klassifizierung — Regeln

Klassifiziere das vorliegende Dokument anhand der extrahierten Daten in einen der folgenden Typen.

## Dokumenttypen

### `invoice` — Eingangsrechnung
**Erkennungsmerkmale:**
- Enthält "Rechnung", "Invoice", "Rechnungsnummer", "Rechnungsdatum"
- Hat einen Rechnungssteller (Lieferant) und einen Rechnungsempfänger
- **Der Rechnungssteller (vendor_name) ist NICHT der Mandant** — die Rechnung kommt von einem externen Lieferanten
- Enthält Nettobetrag, MwSt/USt und Bruttobetrag
- Hat eine Rechnungsnummer
- Oft mit Zahlungsziel, IBAN, Bankverbindung

**Buchungsrichtung:** Aufwand (Soll) an Verbindlichkeit (Haben)

### `outgoing_invoice` — Ausgangsrechnung (Einnahme)
**Erkennungsmerkmale:**
- Enthält "Rechnung", "Invoice", "Rechnungsnummer", "Rechnungsdatum"
- **Der Rechnungssteller (vendor_name) IST der Mandant selbst** — der Mandant stellt die Rechnung aus
- Erkennbar daran, dass vendor_name / vendor_tax_number / vendor_vat_id mit den Stammdaten des Mandanten übereinstimmen
- Der Rechnungsempfänger (recipient_name) ist ein Kunde des Mandanten
- Enthält Nettobetrag, MwSt/USt und Bruttobetrag

**Buchungsrichtung:** Forderung (Soll) an Erlös (Haben)

### `credit_note` — Gutschrift
**Erkennungsmerkmale:**
- Enthält "Gutschrift", "Stornorechnung", "Credit Note", "Korrektur"
- Bezieht sich oft auf eine vorherige Rechnungsnummer
- Beträge können negativ dargestellt sein oder als "Gutschrift"
- Selbes Format wie Rechnung, aber explizit als Gutschrift gekennzeichnet

**Buchungsrichtung:** Verbindlichkeit (Soll) an Aufwand (Haben) — umgekehrt zur Rechnung

### `receipt` — Kassenbon / Quittung
**Erkennungsmerkmale:**
- Enthält "Quittung", "Kassenbon", "Beleg", "Bon"
- Oft kürzer und weniger strukturiert als Rechnungen
- Enthält typischerweise Datum, Gesamtbetrag, evtl. MwSt-Ausweis
- Kein formelles Zahlungsziel (sofort bezahlt)
- Oft von Einzelhandel, Tankstellen, Restaurants

**Buchungsrichtung:** Aufwand (Soll) an Kasse/Bank (Haben)

### `bank_statement` — Kontoauszug
**Erkennungsmerkmale:**
- Enthält "Kontoauszug", "Bank Statement", "Auszug Nr."
- Listet mehrere Transaktionen (Soll/Haben) auf
- Zeigt Anfangs- und Endsaldo
- Enthält Buchungsdaten, Verwendungszwecke, Gegenstellen

**Hinweis:** Kontoauszüge werden nicht einzeln gebucht, sondern dienen als Referenz.

### `other` — Sonstige Dokumente
**Erkennungsmerkmale:**
- Keines der obigen Muster trifft zu
- Verträge, Mahnungen, Lieferscheine, Angebote, etc.

**Hinweis:** Diese Dokumente werden zur manuellen Prüfung markiert.

## Entscheidungsbaum

```
Dokument analysieren
├── Enthält "Gutschrift"/"Credit Note"/"Storno"? → credit_note
├── Enthält "Rechnung"/"Invoice" + Rechnungsnummer?
│   ├── vendor_name = Mandant (Stammdaten-Abgleich)? → outgoing_invoice
│   └── vendor_name ≠ Mandant? → invoice
├── Enthält "Kassenbon"/"Quittung"/"Bon"? → receipt
├── Enthält "Kontoauszug"/"Bank Statement"? → bank_statement
└── Nichts davon → other
```

## Confidence-Bewertung

- **> 0.95**: Dokument passt eindeutig zu genau einem Typ
- **0.80–0.95**: Dokument passt wahrscheinlich, aber einige Merkmale fehlen
- **< 0.80**: Unklar — zur manuellen Prüfung markieren
