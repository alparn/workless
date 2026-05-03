"""Rule-based booking validation for SKR03/SKR04 compliance.

Each rule returns a list of ValidationIssue dicts.  The supervisor
collects them, persists auto-fixable ones, and creates notifications
for those requiring human review.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.services.industry_catalog import get_industry_profile

logger = logging.getLogger(__name__)

SKR03_VALID_RANGES: list[tuple[int, int]] = [
    (1, 999),       # Anlage- und Kapitalkonten
    (1000, 1999),   # Finanzkonten (Bank, Kasse)
    (2000, 2999),   # Abgrenzungskonten
    (3000, 3999),   # Wareneingangs- / Materialkonten
    (4000, 4999),   # Betriebliche Aufwendungen
    (5000, 5999),   # Sonstiger Aufwand (selten, aber gültig)
    (6000, 6999),   # Aufwendungen
    (7000, 7999),   # Bestands-/Ertragskonten
    (8000, 8999),   # Erlöse
    (9000, 9999),   # Vortragskonten / Statistik
    (10000, 99999), # Personenkonten (Debitoren/Kreditoren)
]

SKR04_VALID_RANGES: list[tuple[int, int]] = [
    (1, 999),
    (1000, 1999),
    (2000, 2999),
    (3000, 3999),
    (4000, 4999),
    (5000, 5999),
    (6000, 6999),
    (7000, 7999),
    (8000, 8999),
    (9000, 9999),
    (10000, 99999),
]

BANK_ACCOUNTS_SKR03 = set(range(1200, 1300))
BANK_ACCOUNTS_SKR04 = set(range(1800, 1900))


@dataclass
class ValidationIssue:
    booking_id: str
    rule: str
    severity: str  # "error", "warning", "info"
    message: str
    auto_fixable: bool = False
    fix_data: dict | None = None


def validate_booking(
    booking: Booking,
    chart: str = "SKR03",
    all_bookings: list[Booking] | None = None,
    industry: str | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    bid = str(booking.id)

    issues.extend(_check_account_validity(bid, booking.account, "Konto", chart))
    issues.extend(_check_account_validity(bid, booking.contra_account, "Gegenkonto", chart))
    issues.extend(_check_amount(bid, booking))
    issues.extend(_check_debit_credit(bid, booking))
    issues.extend(_check_same_account(bid, booking))
    issues.extend(_check_booking_text(bid, booking))
    issues.extend(_check_industry_plausibility(bid, booking, industry))
    issues.extend(_check_missing_bank_link(bid, booking, chart, all_bookings))
    issues.extend(_check_debtor_without_revenue(bid, booking, chart))

    if all_bookings:
        issues.extend(_check_duplicates(bid, booking, all_bookings))

    return issues


def _check_account_validity(
    bid: str, account: str, label: str, chart: str
) -> list[ValidationIssue]:
    if not account or not account.strip():
        return [ValidationIssue(
            booking_id=bid, rule="missing_account", severity="error",
            message=f"{label} fehlt",
        )]

    try:
        num = int(account)
    except ValueError:
        return [ValidationIssue(
            booking_id=bid, rule="invalid_account_format", severity="error",
            message=f"{label} '{account}' ist keine gültige Kontonummer",
        )]

    ranges = SKR03_VALID_RANGES if chart.upper() == "SKR03" else SKR04_VALID_RANGES
    if not any(lo <= num <= hi for lo, hi in ranges):
        return [ValidationIssue(
            booking_id=bid, rule="account_out_of_range", severity="warning",
            message=f"{label} {account} liegt außerhalb der üblichen {chart}-Kontenbereiche",
        )]

    return []


def _check_amount(bid: str, booking: Booking) -> list[ValidationIssue]:
    issues = []
    if booking.amount <= 0:
        issues.append(ValidationIssue(
            booking_id=bid, rule="invalid_amount", severity="error",
            message=f"Betrag {booking.amount} ist ungültig (muss > 0 sein)",
        ))
    if booking.amount > Decimal("500000"):
        issues.append(ValidationIssue(
            booking_id=bid, rule="unusually_high_amount", severity="warning",
            message=f"Ungewöhnlich hoher Betrag: {booking.amount} EUR",
        ))
    return issues


def _check_debit_credit(bid: str, booking: Booking) -> list[ValidationIssue]:
    if booking.debit_credit not in ("S", "H"):
        return [ValidationIssue(
            booking_id=bid, rule="invalid_debit_credit", severity="error",
            message=f"Ungültiges S/H-Kennzeichen: '{booking.debit_credit}'",
            auto_fixable=True,
            fix_data={"debit_credit": "S"},
        )]
    return []


def _check_same_account(bid: str, booking: Booking) -> list[ValidationIssue]:
    if booking.account == booking.contra_account:
        return [ValidationIssue(
            booking_id=bid, rule="same_account", severity="error",
            message=f"Konto und Gegenkonto sind identisch: {booking.account}",
        )]
    return []


def _check_booking_text(bid: str, booking: Booking) -> list[ValidationIssue]:
    if not booking.booking_text or len(booking.booking_text.strip()) < 3:
        return [ValidationIssue(
            booking_id=bid, rule="missing_booking_text", severity="warning",
            message="Buchungstext fehlt oder ist zu kurz",
        )]
    return []


def _check_missing_bank_link(
    bid: str,
    booking: Booking,
    chart: str,
    all_bookings: list[Booking] | None,
) -> list[ValidationIssue]:
    """Flag invoice bookings that use a creditor contra-account but have no
    corresponding bank payment booking in the system."""
    bank_range = BANK_ACCOUNTS_SKR03 if chart.upper() == "SKR03" else BANK_ACCOUNTS_SKR04
    creditor_min = 70000

    try:
        contra_num = int(booking.contra_account or "")
    except ValueError:
        return []

    if contra_num < creditor_min:
        return []

    try:
        account_num = int(booking.account or "")
    except ValueError:
        return []

    if account_num in bank_range:
        return []

    if not all_bookings:
        return []

    has_bank_counterpart = False
    for other in all_bookings:
        if str(other.id) == bid:
            continue
        try:
            other_acct = int(other.account or "")
            other_contra = int(other.contra_account or "")
        except ValueError:
            continue

        is_bank_involved = other_acct in bank_range or other_contra in bank_range
        amount_matches = other.amount == booking.amount
        text_overlap = (
            booking.booking_text
            and other.booking_text
            and _text_similarity(booking.booking_text, other.booking_text)
        )

        if is_bank_involved and (amount_matches or text_overlap):
            has_bank_counterpart = True
            break

    if has_bank_counterpart:
        return []

    return [ValidationIssue(
        booking_id=bid,
        rule="missing_bank_payment",
        severity="warning",
        message=(
            f"Buchung auf Konto {booking.account} gegen Kreditor {booking.contra_account} "
            f"({booking.amount} EUR, '{booking.booking_text or ''}') hat keine "
            f"zugehörige Bankbuchung. Mögliche Ursachen: "
            f"(1) Kontoauszug mit dieser Zahlung fehlt noch, "
            f"(2) Zahlung erfolgte bar/EC, "
            f"(3) Rechnung noch nicht bezahlt."
        ),
    )]


def _check_debtor_without_revenue(
    bid: str, booking: Booking, chart: str,
) -> list[ValidationIssue]:
    """Warn when a bank receipt is booked against a debtor account instead of
    a revenue account, which causes the amount to be invisible in the P&L."""
    try:
        contra = int(booking.contra_account or "")
        acct = int(booking.account or "")
    except ValueError:
        return []

    bank_range = BANK_ACCOUNTS_SKR03 if chart.upper() == "SKR03" else BANK_ACCOUNTS_SKR04
    debtor_min, debtor_max = 10000, 69999

    if acct in bank_range and debtor_min <= contra <= debtor_max:
        return [ValidationIssue(
            booking_id=bid,
            rule="debtor_without_revenue",
            severity="warning",
            message=(
                f"Zahlungseingang auf Debitor {booking.contra_account} — "
                f"ggf. fehlt die zugehörige Erlösbuchung "
                f"({'8xxx' if chart.upper() == 'SKR03' else '4xxx'}). "
                f"Debitorenkonten sind nur bei offener-Posten-Buchhaltung korrekt."
            ),
        )]
    return []


def _text_similarity(a: str, b: str) -> bool:
    """Simple word-overlap check for matching booking texts."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return False
    overlap = len(words_a & words_b)
    return overlap >= 2 and overlap / min(len(words_a), len(words_b)) > 0.4


def _check_industry_plausibility(
    bid: str, booking: Booking, industry: str | None,
) -> list[ValidationIssue]:
    """Flag bookings that are unusual for the client's industry."""
    if not industry:
        return []

    profile = get_industry_profile(industry)
    if not profile:
        return []

    issues: list[ValidationIssue] = []
    account = booking.account or ""
    text = (booking.booking_text or "").lower()

    hints = profile.validation_hints
    common_accounts = hints.get("common_expense_range", [])

    suspicious_suppliers = hints.get("suspicious_if_no_receipt", [])
    if suspicious_suppliers:
        for supplier in suspicious_suppliers:
            if supplier in text:
                issues.append(ValidationIssue(
                    booking_id=bid,
                    rule="industry_suspicious_supplier",
                    severity="warning",
                    message=(
                        f"'{supplier.title()}' im Buchungstext — bei Branche "
                        f"'{profile.label}' evtl. nicht betrieblich. Beleg prüfen."
                    ),
                ))

    food_suppliers = hints.get("food_suppliers", [])
    if food_suppliers and industry != "gastro":
        for supplier in food_suppliers:
            if supplier in text and account.startswith("465"):
                issues.append(ValidationIssue(
                    booking_id=bid,
                    rule="industry_food_non_gastro",
                    severity="warning",
                    message=(
                        f"Wareneinkauf Lebensmittel (Konto {account}) bei "
                        f"'{profile.label}' — nur zulässig als Bewirtung (4654)."
                    ),
                ))

    return issues


def _check_duplicates(
    bid: str, booking: Booking, all_bookings: list[Booking]
) -> list[ValidationIssue]:
    issues = []
    for other in all_bookings:
        if str(other.id) == bid:
            continue
        if (
            other.amount == booking.amount
            and other.account == booking.account
            and other.contra_account == booking.contra_account
            and other.document_date == booking.document_date
            and other.debit_credit == booking.debit_credit
        ):
            issues.append(ValidationIssue(
                booking_id=bid, rule="possible_duplicate", severity="warning",
                message=(
                    f"Mögliches Duplikat: gleicher Betrag ({booking.amount}), "
                    f"gleiches Datum ({booking.document_date}), gleiche Konten "
                    f"({booking.account}/{booking.contra_account}) "
                    f"wie Buchung {str(other.id)[:8]}…"
                ),
            ))
    return issues


async def validate_client_bookings(
    db: AsyncSession, client_id: str, chart: str = "SKR03",
    only_status: str = "suggested", industry: str | None = None,
) -> list[ValidationIssue]:
    """Validate all bookings of a given status for a client.

    Also loads all non-exported bookings as cross-reference context so that
    checks like missing_bank_payment can see bank transactions even if the
    target bookings are filtered by status.
    """
    import uuid
    cid = uuid.UUID(client_id)

    result = await db.execute(
        select(Booking)
        .where(Booking.client_id == cid)
        .where(Booking.status == only_status)
        .order_by(Booking.document_date)
    )
    target_bookings = list(result.scalars().all())

    all_result = await db.execute(
        select(Booking)
        .where(Booking.client_id == cid)
        .where(Booking.status.in_(["suggested", "approved", "exported"]))
        .order_by(Booking.document_date)
    )
    all_bookings = list(all_result.scalars().all())

    all_issues: list[ValidationIssue] = []
    for b in target_bookings:
        all_issues.extend(validate_booking(b, chart, all_bookings, industry=industry))
    return all_issues
