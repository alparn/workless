import unicodedata
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.audit_log import AuditLog
from app.models.booking import Booking
from app.models.client import Client
from app.models.export_batch import ExportBatch

EXTF_VERSION = "700"
FORMAT_CATEGORY = 21
FORMAT_NAME = "Buchungsstapel"
FORMAT_VERSION = 12

# Buchungen nach Freigabe oder nachträglicher Korrektur (Chat) — exportierbar wie „approved“.
EXPORTABLE_BOOKING_STATUSES: tuple[str, ...] = ("approved", "corrected")

_EXTF_CHAR_REPLACEMENTS = str.maketrans(
    {
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201a": "'",
        "\u2018": "'",
        "\u2019": "'",
        "\u2032": "'",
        "\u2033": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
        "\u202f": " ",
    }
)


def _normalize_extf_text(content: str) -> str:
    """Map common Unicode punctuation to CP1252-friendly forms before encode."""
    return unicodedata.normalize("NFC", content).translate(_EXTF_CHAR_REPLACEMENTS)


def _format_amount(amount: Decimal) -> str:
    """Always positive, comma as decimal separator, two fractional digits."""
    q = abs(amount).quantize(Decimal("0.01"))
    return format(q, "f").replace(".", ",")


def _format_date_ddmm(d: date) -> str:
    return d.strftime("%d%m")


def _format_date_yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _escape_field(value: str | None) -> str:
    if value is None:
        return ""
    value = value.replace('"', '""')
    if ";" in value or '"' in value or "\n" in value:
        return f'"{value}"'
    return value


def _build_header_line(batch: ExportBatch, created_at: datetime) -> str:
    """DATEV EXTF header (line 1): 32 fields."""
    fields: list[str] = [
        '"EXTF"',                                           # 1  Format-Kennzeichen
        EXTF_VERSION,                                       # 2  Versionsnummer
        str(FORMAT_CATEGORY),                               # 3  Formatkategorie
        f'"{FORMAT_NAME}"',                                 # 4  Formatname
        str(FORMAT_VERSION),                                # 5  Formatversion
        created_at.strftime("%Y%m%d%H%M%S") + "000",       # 6  Erzeugt am (17-stellig)
        "",                                                 # 7  Importiert (leer)
        '"RE"',                                             # 8  Herkunft
        '""',                                               # 9  Exportiert von
        '""',                                               # 10 Importiert von
        str(batch.consultant_number),                       # 11 Berater-Nr.
        str(batch.client_number),                           # 12 Mandanten-Nr.
        _format_date_yyyymmdd(batch.fiscal_year_start),     # 13 WJ-Beginn
        str(batch.account_length),                          # 14 Sachkontenlänge
        _format_date_yyyymmdd(batch.date_from),             # 15 Datum von
        _format_date_yyyymmdd(batch.date_to),               # 16 Datum bis
        f'"{batch.label or ""}"',                           # 17 Bezeichnung
        '""',                                               # 18 Diktatkürzel
        "1",                                                # 19 Buchungstyp (1=Fibu)
        "0",                                                # 20 Rechnungslegungszweck
        "0",                                                # 21 Festschreibung (0=nicht festgeschrieben)
        '"EUR"',                                             # 22 WKZ
        "",                                                 # 23 reserviert
        "",                                                 # 24 Derivatskennzeichen
        "",                                                 # 25 reserviert
        "",                                                 # 26 reserviert
        f'"{batch.chart_of_accounts}"',                   # 27 SKR / Kontenrahmen
        "",                                                 # 28 Branchen-Lösungs-Id
        "",                                                 # 29 reserviert
        "",                                                 # 30 reserviert
        "",                                                 # 31 Anwendungsinformation
        "",                                                 # 32 reserviert
    ]
    return ";".join(fields)


COLUMN_HEADERS = [
    "Umsatz (ohne Soll/Haben-Kz)",
    "Soll/Haben-Kennzeichen",
    "WKZ Umsatz",
    "Kurs",
    "Basis-Umsatz",
    "WKZ Basis-Umsatz",
    "Konto",
    "Gegenkonto (ohne BU-Schlüssel)",
    "BU-Schlüssel",
    "Belegdatum",
    "Belegfeld 1",
    "Belegfeld 2",
    "Skonto",
    "Buchungstext",
    "Postensperre",
    "Diverse Adressnummer",
    "Geschäftspartnerbank",
    "Sachverhalt",
    "Zinssperre",
    "Beleglink",
    "Beleginfo - Art 1",
    "Beleginfo - Inhalt 1",
    "Beleginfo - Art 2",
    "Beleginfo - Inhalt 2",
    "Beleginfo - Art 3",
    "Beleginfo - Inhalt 3",
    "Beleginfo - Art 4",
    "Beleginfo - Inhalt 4",
    "Beleginfo - Art 5",
    "Beleginfo - Inhalt 5",
    "Beleginfo - Art 6",
    "Beleginfo - Inhalt 6",
    "Beleginfo - Art 7",
    "Beleginfo - Inhalt 7",
    "Beleginfo - Art 8",
    "Beleginfo - Inhalt 8",
    "KOST1 - Kostenstelle",
    "KOST2 - Kostenstelle",
    "KOST-Menge",
    "EU-Land u. UStID",
    "EU-Steuersatz",
    "Abw. Versteuerungsart",
    "Sachverhalt L+L",
    "Funktionsergänzung L+L",
    "BU 49 Hauptfunktionstyp",
    "BU 49 Hauptfunktionsnummer",
    "BU 49 Funktionsergänzung",
    "Zusatzinformation - Art 1",
    "Zusatzinformation - Inhalt 1",
    "Zusatzinformation - Art 2",
    "Zusatzinformation - Inhalt 2",
    "Zusatzinformation - Art 3",
    "Zusatzinformation - Inhalt 3",
    "Zusatzinformation - Art 4",
    "Zusatzinformation - Inhalt 4",
    "Zusatzinformation - Art 5",
    "Zusatzinformation - Inhalt 5",
    "Zusatzinformation - Art 6",
    "Zusatzinformation - Inhalt 6",
    "Zusatzinformation - Art 7",
    "Zusatzinformation - Inhalt 7",
    "Zusatzinformation - Art 8",
    "Zusatzinformation - Inhalt 8",
    "Zusatzinformation - Art 9",
    "Zusatzinformation - Inhalt 9",
    "Zusatzinformation - Art 10",
    "Zusatzinformation - Inhalt 10",
    "Zusatzinformation - Art 11",
    "Zusatzinformation - Inhalt 11",
    "Zusatzinformation - Art 12",
    "Zusatzinformation - Inhalt 12",
    "Zusatzinformation - Art 13",
    "Zusatzinformation - Inhalt 13",
    "Zusatzinformation - Art 14",
    "Zusatzinformation - Inhalt 14",
    "Zusatzinformation - Art 15",
    "Zusatzinformation - Inhalt 15",
    "Zusatzinformation - Art 16",
    "Zusatzinformation - Inhalt 16",
    "Stück",
    "Gewicht",
    "Zahlweise",
    "Forderungsart",
    "Veranlagungsjahr",
    "Zugeordnete Fälligkeit",
    "Skontotyp",
    "Auftragsnummer",
    "Buchungstyp",
    "USt-Schlüssel (Anzahlungen)",
    "EU-Land (Anzahlungen)",
    "Sachverhalt L+L (Anzahlungen)",
    "EU-Steuersatz (Anzahlungen)",
    "Erlöskonto (Anzahlungen)",
    "Herkunft-Kz",
    "Buchungs GUID",
    "KOST-Datum",
    "SEPA-Mandatsreferenz",
    "Skontosperre",
    "Gesellschaftername",
    "Beteiligtennummer",
    "Identifikationsnummer",
    "Zeichnernummer",
    "Postensperre bis",
    "Bezeichnung SoBil-Sachverhalt",
    "Kennzeichen SoBil-Buchung",
    "Festschreibung",
    "Leistungsdatum",
    "Datum Zuord. Steuerperiode",
    "Fälligkeit",
    "Generalumkehr (GU)",
    "Steuersatz",
    "Land",
    "Abrechnungsreferenz",
    "BVV-Position (Betriebsvermögensvergleich)",
    "EU-Land u. UStID (Anzahlungen)",
    "Sachverhalt L+L (Anzahlungen 2)",
]

assert len(COLUMN_HEADERS) == 116


def _build_column_header_line() -> str:
    return ";".join(COLUMN_HEADERS)


def _build_booking_line(booking: Booking) -> str:
    """Build a single EXTF booking line (116 fields)."""
    fields: list[str] = [""] * 116

    fields[0] = _format_amount(booking.amount)                  # Umsatz
    fields[1] = booking.debit_credit                            # S/H
    fields[2] = "EUR"                                           # WKZ Umsatz
    fields[6] = booking.account                                 # Konto
    fields[7] = booking.contra_account                          # Gegenkonto
    fields[8] = booking.bu_key or ""                            # BU-Schlüssel
    fields[9] = _format_date_ddmm(booking.document_date)        # Belegdatum
    fields[10] = _escape_field(booking.reference_1)             # Belegfeld 1
    fields[11] = _escape_field(booking.reference_2)             # Belegfeld 2
    fields[13] = _escape_field(booking.booking_text)            # Buchungstext
    fields[36] = _escape_field(booking.cost_center_1)           # KOST1
    fields[37] = _escape_field(booking.cost_center_2)           # KOST2

    return ";".join(fields)


def generate_extf_content(
    batch: ExportBatch,
    bookings: list[Booking],
) -> bytes:
    """Generate a complete DATEV EXTF file as CP1252-encoded bytes."""
    now = datetime.now(timezone.utc)
    lines: list[str] = [
        _build_header_line(batch, now),
        _build_column_header_line(),
    ]
    for booking in bookings:
        lines.append(_build_booking_line(booking))

    content = "\r\n".join(lines) + "\r\n"
    return _normalize_extf_text(content).encode("cp1252", errors="replace")


async def create_export_batch(
    db: AsyncSession,
    client_id: uuid.UUID,
    date_from: date,
    date_to: date,
    label: str | None = None,
) -> ExportBatch:
    """Create a DATEV EXTF export for freigegebene oder korrigierte Buchungen im Zeitraum."""
    client = await db.get(Client, client_id)
    if client is None:
        raise ValueError("Client not found")

    if client.datev_consultant_number is None or client.datev_client_number is None:
        raise ValueError(
            "DATEV-Beraternummer und Mandantennummer müssen konfiguriert sein."
        )

    result = await db.execute(
        select(Booking)
        .where(
            Booking.client_id == client_id,
            Booking.status.in_(EXPORTABLE_BOOKING_STATUSES),
            Booking.document_date >= date_from,
            Booking.document_date <= date_to,
        )
        .order_by(Booking.document_date, Booking.created_at)
    )
    bookings = list(result.scalars().all())

    if not bookings:
        raise ValueError(
            "Keine freigegebenen Buchungen im gewählten Zeitraum."
        )

    batch = ExportBatch(
        client_id=client_id,
        consultant_number=client.datev_consultant_number,
        client_number=client.datev_client_number,
        fiscal_year_start=client.fiscal_year_start,
        chart_of_accounts=client.chart_of_accounts,
        account_length=client.account_length,
        date_from=date_from,
        date_to=date_to,
        label=label,
        booking_count=len(bookings),
    )
    db.add(batch)
    await db.flush()

    file_content = generate_extf_content(batch, bookings)

    export_dir = settings.export_dir
    export_dir.mkdir(parents=True, exist_ok=True)
    filename = f"EXTF_{batch.id}.csv"
    file_path = export_dir / filename
    file_path.write_bytes(file_content)

    batch.storage_path = str(file_path)
    batch.is_locked = True

    now = datetime.now(timezone.utc)
    for booking in bookings:
        booking.status = "exported"
        booking.exported_at = now
        booking.export_batch_id = batch.id

    audit = AuditLog(
        entity_type="export_batch",
        entity_id=batch.id,
        action="created",
        performed_by="user",
        new_state={
            "client_id": str(client_id),
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "booking_count": len(bookings),
            "booking_ids": [str(b.id) for b in bookings],
        },
    )
    db.add(audit)

    await db.flush()
    await db.refresh(batch)
    return batch
