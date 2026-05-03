"""Prompt templates for booking suggestion nodes.

Kept separate from node logic so prompts are easy to review and adjust
without touching business logic.
"""

import json

# ---------------------------------------------------------------------------
# JSON schema shared between invoice and bank-statement prompts
# ---------------------------------------------------------------------------

_BOOKING_JSON_SCHEMA = """\
{
  "bookings": [
    {
      "amount": decimal (Bruttobetrag, immer positiv),
      "debit_credit": "S" oder "H",
      "account": "Sachkonto/Personenkonto",
      "contra_account": "Gegenkonto",
      "bu_key": "BU-Schlüssel oder null",
      "booking_text": "Max 60 Zeichen",
      "document_date": "YYYY-MM-DD",
      "reference_1": "Rechnungsnummer oder null",
      "reasoning": "Warum dieses Konto?",
      "transaction_index": integer (nur bei Kontoauszügen),
      "needs_clarification": true oder false,
      "clarification_category": "Kategorie oder null",
      "clarification_question": "Frage oder null",
      "tax_hints": {
        "deductibility": "full | partial | none",
        "deductible_percent": integer (0-100),
        "hint": "Kurzer Hinweis zur steuerlichen Behandlung oder null",
        "action_required": "Fehlender Nachweis oder nötige Aktion oder null",
        "legal_basis": "Rechtsgrundlage z.B. § 4 Abs. 5 Nr. 2 EStG oder null"
      }
    }
  ],
  "overall_confidence": 0.0-1.0,
  "overall_reasoning": "Zusammenfassung"
}"""


_INVOICE_RULES = """\
Regeln:
- Bruttobetrag verwenden, BU-Schlüssel übernimmt die MwSt-Aufteilung
- Bei gemischten MwSt-Sätzen: separate Buchungszeile pro Satz
- Konto = Aufwandskonto (z.B. 4930 Bürobedarf)
- Gegenkonto = Kreditor (z.B. 70001) oder Verbindlichkeiten (3300)
- S/H bezieht sich auf das Konto (Spalte 7 in DATEV)
- Booking text: 'Lieferant Kurzbeschreibung'

Steuerliche Absetzbarkeit — prüfe für JEDE Buchung und fülle tax_hints aus:
- Bewirtungskosten (4650/4654): 70% absetzbar (§ 4 Abs. 5 Nr. 2 EStG), \
Bewirtungsbeleg mit Teilnehmerliste erforderlich. Aufmerksamkeiten unter 60 EUR: 100% absetzbar.
- Geschenke (4630): bis 50 EUR/Person/Jahr absetzbar (§ 4 Abs. 5 Nr. 1 EStG)
- GWG (0480/0670): sofort absetzbar bis 800 EUR netto (§ 6 Abs. 2 EStG)
- Fortbildung/Fachliteratur: 100% absetzbar wenn berufsbezogen
- Telefon/Internet bei gemischter Nutzung: typisch 20-50% privat, Aufteilung dokumentieren
- Kfz-Kosten: Privatanteil beachten (1%-Regelung oder Fahrtenbuch)
- Bei Teilabzügen berechne den korrekten Prozentsatz in deductible_percent
- Bei fehlenden Nachweisen (Bewirtungsbeleg, Fahrtenbuch) weise in action_required darauf hin
- Wenn nicht steuerlich relevant (z.B. durchlaufender Posten): deductibility = "none\""""


_OUTGOING_INVOICE_RULES = """\
Regeln für AUSGANGSRECHNUNGEN (Einnahme/Erlös):
- Dies ist eine Rechnung, die der Mandant selbst an einen Kunden gestellt hat → EINNAHME
- Bruttobetrag verwenden, BU-Schlüssel übernimmt die MwSt-Aufteilung
- Bei gemischten MwSt-Sätzen: separate Buchungszeile pro Satz
- Konto = Forderungskonto (SKR03: 1200 Forderungen aus LuL; SKR04: 1200)
  oder Debitorenkonto (z.B. 10001) bei offener-Posten-Buchhaltung
- Gegenkonto = Erlöskonto (SKR03: 8400 Erlöse 19% USt, 8300 Erlöse 7% USt; \
SKR04: 4400 Erlöse 19% USt, 4300 Erlöse 7% USt)
- S/H: Forderung (S) an Erlös (H)
- Booking text: 'Kunde Kurzbeschreibung' oder 'AR-Nr Kunde'

Steuerliche Behandlung:
- Erlöse sind KEINE Betriebsausgabe → deductibility = "none"
- tax_hints.hint: "Umsatzerlös — umsatzsteuerpflichtig" oder "Umsatzerlös — steuerfrei" \
je nach Sachverhalt
- Reverse Charge (§ 13b UStG): Wenn der Kunde im EU-Ausland sitzt und eine gültige USt-IdNr. hat, \
kein BU-Schlüssel, Erlöskonto für steuerfreie innergemeinschaftliche Lieferung verwenden \
(SKR03: 8125/8338; SKR04: 4125/4338)
- Kleinunternehmer (§ 19 UStG): Kein MwSt-Ausweis, kein BU-Schlüssel"""


_BANK_STATEMENT_RULES_TEMPLATE = """\
Regeln für Kontoauszug-Buchungen:
- Bankkonto ist **{bank_account}** ({bank_name}) — verwende dieses als Gegenkonto
- Belastungen (negative Beträge): Aufwandskonto (S) an Bankkonto (H)
  z.B. Bankgebühren: 4969 (S) an {bank_account} (H)
  z.B. Miete: 4210 (S) an {bank_account} (H)
- Gutschriften/Zahlungseingänge von Kunden (positive Beträge):
  Bankkonto (S) an Erlöskonto (H)
  z.B. Zahlungseingang Kunde: {bank_account} (S) an Erlöskonto (H) mit BU-Schlüssel
  WICHTIG: Für Umsatzerlöse IMMER ein Erlöskonto als Gegenkonto verwenden \
(SKR03: 8xxx z.B. 8400; SKR04: 4xxx z.B. 4400), NICHT ein Debitorenkonto (10000+). \
Debitorenkonten (10000–69999) nur bei offener-Posten-Buchhaltung verwenden.
- Bankgebühren: Konto 4969, kein BU-Schlüssel (steuerfreie Finanzdienstleistung § 4 Nr. 8 UStG)
- Zinsen Soll: Konto 7310, kein BU-Schlüssel
- Zinsen Haben: Konto 7100, kein BU-Schlüssel
- Betrag IMMER positiv, Richtung über debit_credit steuern
- Für JEDE Transaktion genau EINE Buchungszeile
- document_date: Das Buchungsdatum der jeweiligen Transaktion verwenden
- Wenn eine Gegenpartei in den früheren Buchungen auftaucht, verwende bevorzugt \
dasselbe Sachkonto wie zuvor

Steuerliche Absetzbarkeit — prüfe für JEDE Buchung und fülle tax_hints aus:
- Bewirtungskosten (4650/4654): 70% absetzbar (§ 4 Abs. 5 Nr. 2 EStG), \
Bewirtungsbeleg mit Teilnehmerliste erforderlich. Aufmerksamkeiten unter 60 EUR: 100% absetzbar.
- Geschenke (4630): bis 50 EUR/Person/Jahr absetzbar (§ 4 Abs. 5 Nr. 1 EStG)
- GWG (0480/0670): sofort absetzbar bis 800 EUR netto (§ 6 Abs. 2 EStG)
- Bankgebühren (4969): 100% absetzbar als Betriebsausgabe
- Miete/Leasing: 100% absetzbar wenn betrieblich, bei Homeoffice anteilig
- Fortbildung/Fachliteratur: 100% absetzbar wenn berufsbezogen
- Telefon/Internet bei gemischter Nutzung: typisch 20-50% privat, Aufteilung dokumentieren
- Kfz-Kosten: Privatanteil beachten (1%-Regelung oder Fahrtenbuch)
- Privatentnahmen/-einlagen: nicht absetzbar (deductibility = "none")
- Bei Teilabzügen berechne den korrekten Prozentsatz in deductible_percent
- Bei fehlenden Nachweisen (Bewirtungsbeleg, Fahrtenbuch) weise in action_required darauf hin
- Für Erlöse/Zahlungseingänge: deductibility = "none" (kein Aufwand)"""


_CLARIFICATION_RULES = """\
Klärungsbedarf — setze needs_clarification: true wenn EINE dieser Kategorien zutrifft:
- "cash_deposit": Bareinzahlung oder Kasseneinlage — Herkunft der Mittel unklar
- "cash_withdrawal": Barauszahlung oder Geldautomat — betrieblich oder Privatentnahme?
- "owner_transfer": Gegenpartei ist ein Personenname (keine Firma/GmbH/AG/KG/UG/e.K.) \
und Betrag > 200€ — Privatentnahme, Gehalt oder Darlehen?
- "vague_reference": Verwendungszweck hat < 4 Wörter ODER enthält nur Zahlen/Codes \
ODER ist generisch ('Überweisung', 'Transfer', 'Zahlung') bei Betrag > 200€
- "unknown_private_person": Auftraggeber/Empfänger ist offensichtlich eine Privatperson \
(kein Unternehmensname), einmalige Transaktion, Betrag > 100€
- "loan_indicator": Verwendungszweck enthält "Darlehen", "Leihe", "Tilgung", \
"Rückzahlung" ohne erkennbaren Buchungskontext
- "large_unidentified": Betrag ≥ 500€ UND durch 100 teilbar UND Gegenpartei unbekannt/unklar

clarification_question: Formuliere eine präzise, höfliche Frage an den Mandanten auf Deutsch. \
Nenne Datum, Betrag und Gegenpartei. Stelle genau eine geschlossene oder offene Frage. \
Kein Buchhaltungsjargon.
Beispiel: 'Am 15.04.2026 wurde ein Betrag von 1.500,00 € von Max Mustermann eingezahlt. \
Handelt es sich hierbei um eine Privateinlage, ein Darlehen oder einen Zahlungseingang \
aus einem Geschäft?'"""


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------


def build_invoice_prompt(
    skr_skill: str,
    vat_skill: str,
    dynamic_skills: str,
    vendor_context: str,
    extraction: dict,
    industry_context: str = "",
) -> str:
    return (
        f"{skr_skill}\n\n---\n\n{vat_skill}\n\n---\n\n"
        f"{dynamic_skills}"
        f"{industry_context}"
        "Du bist ein erfahrener Buchhalter. Erstelle einen Buchungsvorschlag für das "
        "folgende Dokument.\n"
        "Du kannst execute_python nutzen, um Beträge zu prüfen oder MwSt-Berechnungen zu validieren.\n"
        "Antworte am Ende NUR mit validem JSON.\n\n"
        f"JSON-Format:\n{_BOOKING_JSON_SCHEMA}\n\n"
        f"{_INVOICE_RULES}\n"
        f"{vendor_context}\n\n"
        f"Extrahierte Dokumentdaten:\n{json.dumps(extraction, default=str, indent=2)}"
    )


def build_outgoing_invoice_prompt(
    skr_skill: str,
    vat_skill: str,
    dynamic_skills: str,
    customer_context: str,
    extraction: dict,
    industry_context: str = "",
) -> str:
    return (
        f"{skr_skill}\n\n---\n\n{vat_skill}\n\n---\n\n"
        f"{dynamic_skills}"
        f"{industry_context}"
        "Du bist ein erfahrener Buchhalter. Erstelle einen Buchungsvorschlag für die "
        "folgende AUSGANGSRECHNUNG (Einnahme).\n"
        "WICHTIG: Dies ist eine Rechnung, die der Mandant an einen Kunden gestellt hat. "
        "Die Buchung muss als ERLÖS/EINNAHME erfolgen, NICHT als Aufwand!\n"
        "Du kannst execute_python nutzen, um Beträge zu prüfen oder MwSt-Berechnungen zu validieren.\n"
        "Antworte am Ende NUR mit validem JSON.\n\n"
        f"JSON-Format:\n{_BOOKING_JSON_SCHEMA}\n\n"
        f"{_OUTGOING_INVOICE_RULES}\n"
        f"{customer_context}\n\n"
        f"Extrahierte Dokumentdaten:\n{json.dumps(extraction, default=str, indent=2)}"
    )


def build_bank_statement_prompt(
    skr_skill: str,
    vat_skill: str,
    dynamic_skills: str,
    bank_account: str,
    bank_name: str,
    vendor_context: str,
    bank_resolution_note: str,
    transactions: list[dict],
    industry_context: str = "",
) -> str:
    rules = _BANK_STATEMENT_RULES_TEMPLATE.format(
        bank_account=bank_account,
        bank_name=bank_name,
    )

    return (
        f"{skr_skill}\n\n---\n\n{vat_skill}\n\n---\n\n"
        f"{dynamic_skills}"
        f"{industry_context}"
        "Du bist ein erfahrener Buchhalter. Du erhältst einen Kontoauszug mit mehreren Transaktionen.\n"
        "Erstelle für JEDE Transaktion einen separaten Buchungsvorschlag. "
        "Antworte NUR mit validem JSON.\n\n"
        f"JSON-Format:\n{_BOOKING_JSON_SCHEMA}\n\n"
        f"{rules}\n\n"
        f"{_CLARIFICATION_RULES}\n\n"
        f"Bankname: {bank_name}\n"
        f"{vendor_context}"
        f"{bank_resolution_note}"
        f"\nTransaktionen:\n{json.dumps(transactions, default=str, indent=2)}"
    )
