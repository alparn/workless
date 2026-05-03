"""
Industry catalog — branch-specific accounting rules and typical accounts.

Each industry defines:
- label: German display name
- prompt_context: injected into every LLM booking prompt
- typical_expense_accounts: common expense accounts (SKR03)
- typical_revenue_accounts: common revenue accounts (SKR03)
- starter_skills: auto-created skills when a client is set up
- validation_hints: used by the Prüfer for plausibility checks
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IndustryProfile:
    key: str
    label: str
    prompt_context: str
    typical_expense_accounts: dict[str, str] = field(default_factory=dict)
    typical_revenue_accounts: dict[str, str] = field(default_factory=dict)
    default_vat_rate: str = "19"
    starter_skills: list[dict] = field(default_factory=list)
    validation_hints: dict = field(default_factory=dict)


INDUSTRY_PROFILES: dict[str, IndustryProfile] = {

    "gastro": IndustryProfile(
        key="gastro",
        label="Gastronomie & Hotellerie",
        prompt_context=(
            "BRANCHENKONTEXT: Gastronomie-Betrieb.\n"
            "- Wareneinkauf Lebensmittel → 4650 (7% USt, BU 9) oder 4660 (19% USt, BU 8) je nach Produkt\n"
            "- Getränke (alkoholisch) → 4660 mit 19% USt\n"
            "- Lebensmittel-Grundnahrungsmittel, Gemüse, Fleisch, Fisch → 4650 mit 7% USt\n"
            "- Erlöse Speisen (Außer-Haus) → 8300 mit 7% USt\n"
            "- Erlöse Speisen (im Haus) → 8400 mit 19% USt\n"
            "- Erlöse Getränke → 8400 mit 19% USt\n"
            "- Reinigungsmittel, Hygiene → 4250\n"
            "- Küchengeräte, Kleingeräte → 4980 oder Anlagevermögen\n"
            "- Berufskleidung (Kochjacken, Schürzen) → 4964\n"
            "- METRO, EDEKA, REWE, Selgros = typische Gastro-Lieferanten → Wareneinkauf\n"
            "- Lieferando, Wolt Provisionen → 4760 (Vertriebskosten)\n"
        ),
        typical_expense_accounts={
            "4650": "Wareneinkauf 7% USt (Lebensmittel)",
            "4660": "Wareneinkauf 19% USt (Getränke, Non-Food)",
            "4250": "Reinigung",
            "4210": "Miete Geschäftsräume",
            "4964": "Berufskleidung",
            "4980": "Betriebsbedarf",
            "4760": "Vertriebskosten",
        },
        typical_revenue_accounts={
            "8300": "Erlöse 7% USt (Speisen Außer-Haus)",
            "8400": "Erlöse 19% USt (Speisen im Haus, Getränke)",
        },
        default_vat_rate="19",
        starter_skills=[
            {
                "skill_key": "industry:gastro:wareneinkauf",
                "category": "industry_pattern",
                "title": "Gastro: Wareneinkauf Lebensmittel",
                "content": (
                    "Lebensmittel (Gemüse, Fleisch, Fisch, Milch, Brot) → Konto 4650, BU 9 (7% USt).\n"
                    "Getränke (Bier, Wein, Spirituosen, Softdrinks) → Konto 4660, BU 8 (19% USt).\n"
                    "Typische Lieferanten: METRO, Selgros, EDEKA Foodservice, Transgourmet."
                ),
            },
            {
                "skill_key": "industry:gastro:erloese",
                "category": "industry_pattern",
                "title": "Gastro: Erlös-Unterscheidung",
                "content": (
                    "Speisen zum Mitnehmen → 8300 (7% USt). Speisen im Restaurant → 8400 (19% USt).\n"
                    "Getränke immer 8400 (19% USt). Lieferdienst-Erlöse → 8300 (7%)."
                ),
            },
        ],
        validation_hints={
            "common_expense_range": ["4210", "4250", "4650", "4660", "4760", "4964", "4980"],
            "food_suppliers": ["metro", "selgros", "edeka", "rewe", "transgourmet", "chefs culinar"],
        },
    ),

    "it_services": IndustryProfile(
        key="it_services",
        label="IT & Software",
        prompt_context=(
            "BRANCHENKONTEXT: IT-Dienstleistung / Softwareunternehmen.\n"
            "- SaaS-/Cloud-Abos (AWS, Azure, Google Cloud, Hetzner) → 4964 (EDV-Kosten) oder 4806\n"
            "- Software-Lizenzen → 4964\n"
            "- Hardware (Laptops, Server, Monitore) → 0650/0670 (Anlagevermögen) oder 4980 (GWG < 800€)\n"
            "- Freelancer/Subunternehmer → 4909 (Fremdleistungen)\n"
            "- Domains, Hosting → 4964\n"
            "- Erlöse Dienstleistungen → 8400 (19% USt)\n"
            "- Erlöse EU/Drittland → 8338/8338 (steuerfrei bei korrekter Reverse-Charge)\n"
            "- Lebensmitteleinkäufe sind KEINE Betriebsausgaben (privat!), "
            "es sei denn als Bewirtung (4654) mit Bewirtungsbeleg\n"
        ),
        typical_expense_accounts={
            "4964": "EDV-Kosten, Software, Lizenzen",
            "4806": "Wartung, Updates",
            "4909": "Fremdleistungen (Freelancer)",
            "4980": "GWG / Betriebsbedarf",
            "4930": "Bürobedarf",
            "4210": "Miete (Büro/Coworking)",
            "4654": "Bewirtungskosten (70%)",
        },
        typical_revenue_accounts={
            "8400": "Erlöse 19% USt",
            "8338": "Erlöse EU steuerfrei (Reverse Charge)",
        },
        starter_skills=[
            {
                "skill_key": "industry:it:cloud_hosting",
                "category": "industry_pattern",
                "title": "IT: Cloud & Hosting Kosten",
                "content": (
                    "AWS, Azure, Google Cloud, Hetzner, DigitalOcean → Konto 4964 (EDV-Kosten).\n"
                    "Domain-Registrierung, SSL-Zertifikate → 4964.\n"
                    "Bei EU-Anbietern ohne dt. USt: Reverse Charge beachten (BU 94/95)."
                ),
            },
            {
                "skill_key": "industry:it:no_food_expense",
                "category": "industry_pattern",
                "title": "IT: Lebensmittel sind keine Betriebsausgabe",
                "content": (
                    "Supermarkt-Einkäufe (REWE, EDEKA, Aldi, Lidl, METRO) bei IT-Firmen sind "
                    "in der Regel NICHT betrieblich. Nur mit Bewirtungsbeleg → 4654 (70% absetzbar).\n"
                    "Bei Klärungsbedarf: needs_clarification = true setzen."
                ),
            },
        ],
        validation_hints={
            "common_expense_range": ["4210", "4654", "4806", "4909", "4930", "4964", "4980"],
            "suspicious_if_no_receipt": ["metro", "rewe", "edeka", "aldi", "lidl"],
        },
    ),

    "handel": IndustryProfile(
        key="handel",
        label="Handel (Einzel-/Großhandel)",
        prompt_context=(
            "BRANCHENKONTEXT: Handelsunternehmen.\n"
            "- Wareneinkauf → 3200-3999 (Wareneingang), typisch 3200 (7%) / 3400 (19%)\n"
            "- Frachtkosten → 3800 (Bezugsnebenkosten)\n"
            "- Verpackung → 4910\n"
            "- Erlöse → 8100 (steuerfrei) / 8300 (7%) / 8400 (19%)\n"
            "- Amazon/eBay Gebühren → 4760\n"
            "- Lagerkosten → 4210 oder 4290\n"
        ),
        typical_expense_accounts={
            "3200": "Wareneingang 7% USt",
            "3400": "Wareneingang 19% USt",
            "3800": "Bezugsnebenkosten (Fracht)",
            "4760": "Verkaufsprovisionen",
            "4910": "Verpackungsmaterial",
            "4210": "Miete (Lager/Geschäft)",
        },
        typical_revenue_accounts={
            "8300": "Erlöse 7% USt",
            "8400": "Erlöse 19% USt",
        },
        starter_skills=[
            {
                "skill_key": "industry:handel:wareneinkauf",
                "category": "industry_pattern",
                "title": "Handel: Wareneinkauf",
                "content": (
                    "Wareneinkauf 7% → 3200 (BU 9). Wareneinkauf 19% → 3400 (BU 8).\n"
                    "Frachtkosten → 3800 (Bezugsnebenkosten).\n"
                    "Amazon/eBay Gebühren → 4760 (Verkaufsprovisionen)."
                ),
            },
        ],
        validation_hints={
            "common_expense_range": ["3200", "3400", "3800", "4210", "4760", "4910"],
        },
    ),

    "handwerk": IndustryProfile(
        key="handwerk",
        label="Handwerk & Bau",
        prompt_context=(
            "BRANCHENKONTEXT: Handwerks-/Baubetrieb.\n"
            "- Materialeinkauf → 3200/3400 (Roh-/Hilfsstoffe)\n"
            "- Werkzeug < 800€ → 4980 (GWG), > 800€ → 0650 (Anlagevermögen)\n"
            "- Fahrzeugkosten → 4510-4580\n"
            "- Subunternehmer → 4909 (Fremdleistungen)\n"
            "- Arbeitsschutzkleidung → 4964\n"
            "- Bauleistungen: §13b Reverse Charge beachten\n"
        ),
        typical_expense_accounts={
            "3200": "Materialeinkauf 7%",
            "3400": "Materialeinkauf 19%",
            "4909": "Fremdleistungen / Subunternehmer",
            "4510": "Kfz-Steuern",
            "4530": "Kfz-Betriebskosten",
            "4980": "GWG / Werkzeug",
            "4964": "Berufskleidung / Arbeitsschutz",
        },
        typical_revenue_accounts={
            "8400": "Erlöse 19% USt",
        },
        starter_skills=[],
        validation_hints={
            "common_expense_range": ["3200", "3400", "4510", "4530", "4909", "4964", "4980"],
        },
    ),

    "beratung": IndustryProfile(
        key="beratung",
        label="Beratung & Dienstleistungen",
        prompt_context=(
            "BRANCHENKONTEXT: Beratungs-/Dienstleistungsunternehmen.\n"
            "- Kaum Wareneinkauf, hauptsächlich Personalkosten und Sachkosten\n"
            "- Reisekosten → 4660 (Übernachtung), 4670 (Fahrtkosten), 4680 (Verpflegungsmehraufwand)\n"
            "- Bewirtung → 4654 (70% abzugsfähig)\n"
            "- Büromaterial → 4930\n"
            "- Fortbildung → 4945\n"
            "- Erlöse → 8400 (19% USt) für Inlandsberatung\n"
        ),
        typical_expense_accounts={
            "4210": "Miete",
            "4654": "Bewirtungskosten",
            "4660": "Reisekosten Übernachtung",
            "4670": "Reisekosten Fahrtkosten",
            "4680": "Verpflegungsmehraufwand",
            "4930": "Bürobedarf",
            "4945": "Fortbildungskosten",
        },
        typical_revenue_accounts={
            "8400": "Erlöse 19% USt",
            "8338": "Erlöse EU steuerfrei",
        },
        starter_skills=[],
        validation_hints={
            "common_expense_range": ["4210", "4654", "4660", "4670", "4680", "4930", "4945"],
        },
    ),

    "gesundheit": IndustryProfile(
        key="gesundheit",
        label="Gesundheit & Medizin",
        prompt_context=(
            "BRANCHENKONTEXT: Arztpraxis / Gesundheitswesen.\n"
            "- Medizinischer Bedarf → 4980 (Praxisbedarf)\n"
            "- Medizinische Geräte → 0650/0670 (Anlagevermögen)\n"
            "- Labor → 4909 (Fremdleistungen)\n"
            "- Ärztliche Leistungen sind USt-FREI (§4 Nr.14 UStG) → 8120\n"
            "- Nicht-ärztliche Leistungen (Kosmetik, IGeL) → 8400 (19%)\n"
        ),
        typical_expense_accounts={
            "4980": "Praxisbedarf",
            "4909": "Fremdlabor",
            "4210": "Miete Praxis",
        },
        typical_revenue_accounts={
            "8120": "Steuerfreie Umsätze (ärztl. Leistungen)",
            "8400": "Steuerpflichtige Umsätze (IGeL)",
        },
        starter_skills=[],
        validation_hints={
            "common_expense_range": ["4210", "4909", "4980"],
        },
    ),

    "immobilien": IndustryProfile(
        key="immobilien",
        label="Immobilien & Vermietung",
        prompt_context=(
            "BRANCHENKONTEXT: Immobilienverwaltung / Vermietung.\n"
            "- Instandhaltung → 4260\n"
            "- Nebenkosten (Wasser, Strom, Gas) → 4230-4240\n"
            "- Hausverwaltung → 4909\n"
            "- Grundsteuer → 4290\n"
            "- Mieterlöse → 8400 oder 8120 (je nach USt-Option)\n"
            "- Wohnungsvermietung = USt-frei, Gewerbevermietung optional USt-pflichtig\n"
        ),
        typical_expense_accounts={
            "4230": "Gas/Strom/Wasser",
            "4240": "Heizung",
            "4260": "Instandhaltung",
            "4290": "Grundsteuer/Abgaben",
            "4909": "Hausverwaltung",
        },
        typical_revenue_accounts={
            "8120": "Mieterlöse steuerfrei (Wohnung)",
            "8400": "Mieterlöse steuerpflichtig (Gewerbe)",
        },
        starter_skills=[],
        validation_hints={
            "common_expense_range": ["4230", "4240", "4260", "4290", "4909"],
        },
    ),

    "freiberufler": IndustryProfile(
        key="freiberufler",
        label="Freiberufler / Einzelunternehmen",
        prompt_context=(
            "BRANCHENKONTEXT: Freiberufler / Einzelunternehmen.\n"
            "- Privat- und Geschäftssphäre streng trennen!\n"
            "- Privatentnahme → 1800, Privateinlage → 1890\n"
            "- Arbeitszimmer anteilig → 4210 (Miete anteilig)\n"
            "- Telefon/Internet anteilig → 4920\n"
            "- Fahrtkosten → 4670 (30 Ct/km Pauschale oder tatsächliche Kosten)\n"
            "- Erlöse → 8400 (19%) oder 8120 (freiberuflich steuerfrei)\n"
        ),
        typical_expense_accounts={
            "4210": "Miete (anteilig Arbeitszimmer)",
            "4920": "Telefon/Internet",
            "4670": "Fahrtkosten",
            "4930": "Bürobedarf",
            "1800": "Privatentnahmen",
        },
        typical_revenue_accounts={
            "8400": "Erlöse 19% USt",
        },
        starter_skills=[],
        validation_hints={
            "common_expense_range": ["1800", "1890", "4210", "4670", "4920", "4930"],
        },
    ),
}

INDUSTRY_CHOICES_LABELED: list[dict[str, str]] = [
    {"key": p.key, "label": p.label}
    for p in INDUSTRY_PROFILES.values()
]


def get_industry_profile(key: str | None) -> IndustryProfile | None:
    if not key:
        return None
    return INDUSTRY_PROFILES.get(key)


def get_industry_prompt_context(key: str | None) -> str:
    profile = get_industry_profile(key)
    if not profile:
        return ""
    extra = ""
    if profile.industry_detail if hasattr(profile, "industry_detail") else False:
        extra = f"\nZusätzliche Brancheninfos: {profile.industry_detail}\n"
    return f"\n{profile.prompt_context}{extra}\n"


def build_industry_context(industry: str | None, industry_detail: str | None) -> str:
    """Build the full industry context string for LLM prompts."""
    profile = get_industry_profile(industry)
    if not profile:
        if industry_detail:
            return f"\nBRANCHENKONTEXT: {industry_detail}\n"
        return ""

    detail_part = ""
    if industry_detail:
        detail_part = f"\nZusätzliche Brancheninfos vom Mandanten: {industry_detail}\n"

    return f"\n{profile.prompt_context}{detail_part}\n"
