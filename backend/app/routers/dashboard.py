import uuid
from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.booking import Booking
from app.models.client import Client
from app.models.document import Document
from app.models.export_batch import ExportBatch
from app.schemas.dashboard import (
    AccountBreakdown,
    ActivityEntry,
    DashboardStats,
    FinancialDashboard,
    MonthlyAmount,
    TopVendor,
)
from app.services.booking_validator import BANK_ACCOUNTS_SKR03, BANK_ACCOUNTS_SKR04
from app.services.industry_catalog import get_industry_profile

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

ACTION_LABELS: dict[str, str] = {
    "created": "erstellt",
    "updated": "bearbeitet",
    "approved": "freigegeben",
    "rejected": "abgelehnt",
    "exported": "exportiert",
    "ocr_completed": "OCR abgeschlossen",
    "booking_suggested": "Buchungsvorschlag erstellt",
}

ENTITY_LABELS: dict[str, str] = {
    "booking": "Buchung",
    "document": "Dokument",
    "export_batch": "Export",
}


@router.get("/{client_id}/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> DashboardStats:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    doc_count_result = await db.execute(
        select(sqlfunc.count(Document.id)).where(Document.client_id == client_id)
    )
    doc_count = doc_count_result.scalar() or 0

    booking_counts_result = await db.execute(
        select(Booking.status, sqlfunc.count(Booking.id))
        .where(Booking.client_id == client_id)
        .group_by(Booking.status)
    )
    booking_by_status: dict[str, int] = {
        row[0]: row[1] for row in booking_counts_result.all()
    }
    total_bookings = sum(booking_by_status.values())

    export_count_result = await db.execute(
        select(sqlfunc.count(ExportBatch.id)).where(
            ExportBatch.client_id == client_id
        )
    )
    export_count = export_count_result.scalar() or 0

    return DashboardStats(
        document_count=doc_count,
        booking_count=total_bookings,
        pending_reviews=booking_by_status.get("suggested", 0),
        approved_bookings=booking_by_status.get("approved", 0),
        exported_bookings=booking_by_status.get("exported", 0),
        total_export_batches=export_count,
    )


# GuV-/Kontenklassen müssen zum Mandantenrahmen passen — SKR03 und SKR04 unterscheiden sich.
# Siehe Skills skr03.md (Erlös Klasse 8 ≈ 8xxx; Aufwand 3–6 xxx) vs skr04.md (Erlös Klasse 4 =
# 4xxx; Ware/Personal/Betrieb 5–6 xxx).

_SKR03_EXPENSE_RANGES = [
    (3000, 6999),
    (7300, 7399),  # Verluste aus Abgang Anlagevermögen
    (7400, 7499),  # Forderungsverluste
    (7500, 7599),  # Abschreibungen auf Forderungen
    (7700, 7999),  # Abschreibungen auf Finanzanlagen
]
_SKR03_REVENUE_RANGES = [
    (7000, 7299),  # Beteiligungserträge, Zinserträge, Wertpapiererträge
    (7600, 7699),  # Periodenfremde Erträge, Erstattungen
    (8000, 8999),  # Umsatzerlöse
]

_SKR04_EXPENSE_RANGES = [
    (5000, 6999),
    (7300, 7399),
    (7400, 7499),
    (7500, 7599),
    (7700, 7999),
]
_SKR04_REVENUE_RANGES = [
    (4000, 4999),  # Umsatzerlöse (z. B. 4300, 4400)
    (7000, 7299),  # Beteiligungserträge, Zinserträge
    (7600, 7699),  # Periodenfremde Erträge
]

_DEBTOR_RANGE = (10000, 69999)

_BANK_ACCOUNTS = {
    "SKR03": BANK_ACCOUNTS_SKR03,
    "SKR04": BANK_ACCOUNTS_SKR04,
}


def dashboard_pl_ranges(chart: str | None) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    c = (chart or "SKR03").strip().upper()
    if c == "SKR04":
        return (_SKR04_EXPENSE_RANGES, _SKR04_REVENUE_RANGES)
    return (_SKR03_EXPENSE_RANGES, _SKR03_REVENUE_RANGES)

SKR03_ACCOUNT_LABELS: dict[str, str] = {
    "3200": "Wareneingang 7%",
    "3400": "Wareneingang 19%",
    "3800": "Bezugsnebenkosten",
    "7000": "Erträge aus Beteiligungen",
    "7100": "Zinserträge",
    "7200": "Erträge aus Wertpapieren",
    "7300": "Erträge aus Abgang Anlagevermögen",
    "7310": "Zinsaufwendungen",
    "7400": "Forderungsverluste",
    "7600": "Periodenfremde Erträge",
    "7610": "Sonstige betriebliche Erträge",
    "7640": "Erstattung betrieblicher Steuern",
    "7680": "Erträge aus der Auflösung von Rückstellungen",
    "4210": "Miete",
    "4230": "Gas/Strom/Wasser",
    "4240": "Heizung",
    "4250": "Reinigung",
    "4260": "Instandhaltung",
    "4290": "Grundsteuer/Abgaben",
    "4500": "Fahrzeugkosten",
    "4510": "Kfz-Steuern",
    "4530": "Kfz-Betriebskosten",
    "4654": "Bewirtungskosten",
    "4660": "Reisekosten Übernachtung",
    "4670": "Reisekosten Fahrtkosten",
    "4680": "Verpflegungsmehraufwand",
    "4760": "Verkaufsprovisionen",
    "4806": "Wartung/Updates",
    "4909": "Fremdleistungen",
    "4920": "Telefon/Internet",
    "4930": "Bürobedarf",
    "4945": "Fortbildungskosten",
    "4964": "EDV-Kosten/Berufskleidung",
    "4980": "GWG/Betriebsbedarf",
    "8100": "Erlöse steuerfrei",
    "8120": "Steuerfreie Umsätze",
    "8300": "Erlöse 7%",
    "8338": "Erlöse EU steuerfrei",
    "8400": "Erlöse 19%",
}

SKR04_ACCOUNT_LABELS: dict[str, str] = {
    "4300": "Erlöse 7% USt",
    "4400": "Erlöse 19% USt",
    "7000": "Erträge aus Beteiligungen",
    "7100": "Zinserträge",
    "7300": "Erträge aus Abgang Anlagevermögen",
    "7600": "Periodenfremde Erträge",
    "7610": "Sonstige betriebliche Erträge",
    "6310": "Miete Geschäftsräume",
    "6325": "Gas, Strom, Wasser",
    "6340": "Instandhaltung Geschäftsräume",
    "6500": "Fahrzeugkosten",
    "6800": "Telefon",
    "6815": "Bürobedarf",
    "6825": "Rechts- und Beratungskosten",
    "6830": "Buchführungskosten",
}


def _account_label(account: str, industry: str | None, chart: str | None = None) -> str:
    """Resolve a human-readable label for Sachkonto (SKR03/SKR04)."""
    cr = (chart or "SKR03").strip().upper()
    if cr == "SKR04" and account in SKR04_ACCOUNT_LABELS:
        return SKR04_ACCOUNT_LABELS[account]

    if account in SKR03_ACCOUNT_LABELS:
        return SKR03_ACCOUNT_LABELS[account]

    profile = get_industry_profile(industry)
    if profile:
        for mapping in (profile.typical_expense_accounts, profile.typical_revenue_accounts):
            if account in mapping:
                return mapping[account]

    return f"Konto {account}"


def _in_ranges(num: int, ranges: list[tuple[int, int]]) -> bool:
    return any(lo <= num <= hi for lo, hi in ranges)


def _parse_account_number(raw: str) -> int | None:
    s = raw.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def expense_breakout_account(
    account: str,
    contra_account: str,
    expense_ranges: list[tuple[int, int]],
    revenue_ranges: list[tuple[int, int]],
) -> str | None:
    """Das Aufwandskonto für Aggregationen (bei Bank-Belastung i. d. R. `account`)."""
    acc = _parse_account_number(account)
    contra = _parse_account_number(contra_account)
    acc_exp = acc is not None and _in_ranges(acc, expense_ranges)
    acc_rev = acc is not None and _in_ranges(acc, revenue_ranges)
    contra_exp = contra is not None and _in_ranges(contra, expense_ranges)
    contra_rev = contra is not None and _in_ranges(contra, revenue_ranges)

    # Erlös hat Vorrang, falls Zeile fälschlich in beiden Bereichen landen würde
    if acc_rev or (contra_rev and not acc_rev):
        return None

    if acc_exp:
        return account.strip()
    if contra_exp and not acc_exp:
        return contra_account.strip()
    return None


def _is_debtor(num: int) -> bool:
    return _DEBTOR_RANGE[0] <= num <= _DEBTOR_RANGE[1]


def _is_bank_account(num: int, chart: str | None) -> bool:
    c = (chart or "SKR03").strip().upper()
    return num in _BANK_ACCOUNTS.get(c, BANK_ACCOUNTS_SKR03)


def revenue_breakout_account(
    account: str,
    contra_account: str,
    expense_ranges: list[tuple[int, int]],
    revenue_ranges: list[tuple[int, int]],
    chart: str | None = None,
) -> str | None:
    """Das Erlöskonto für Aggregationen (bei Bank-Gutschrift oft `contra_account`).

    Erkennt auch Buchungen Bank (S) an Debitor (H) als Revenue-Fallback,
    da diese bei Mandanten ohne offene-Posten-Buchhaltung Zahlungseingänge
    darstellen.
    """
    acc = _parse_account_number(account)
    contra = _parse_account_number(contra_account)
    acc_rev = acc is not None and _in_ranges(acc, revenue_ranges)
    contra_rev = contra is not None and _in_ranges(contra, revenue_ranges)
    acc_exp = acc is not None and _in_ranges(acc, expense_ranges)
    contra_exp = contra is not None and _in_ranges(contra, expense_ranges)

    if acc_exp or (contra_exp and not acc_exp):
        return None

    if acc_rev:
        return account.strip()
    if contra_rev and not acc_rev:
        return contra_account.strip()

    if (
        acc is not None
        and contra is not None
        and _is_bank_account(acc, chart)
        and _is_debtor(contra)
    ):
        return contra_account.strip()

    return None


@router.get("/{client_id}/financial", response_model=FinancialDashboard)
async def get_financial_dashboard(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FinancialDashboard:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    result = await db.execute(
        select(Booking).where(
            Booking.client_id == client_id,
            Booking.status.in_(["suggested", "approved", "exported", "corrected"]),
        )
    )
    bookings = result.scalars().all()

    exp_ranges, rev_ranges = dashboard_pl_ranges(client.chart_of_accounts)

    monthly_map: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"expenses": Decimal("0"), "revenue": Decimal("0")}
    )
    account_totals: dict[str, Decimal] = defaultdict(Decimal)
    vendor_data: dict[str, dict] = defaultdict(lambda: {"total": Decimal("0"), "count": 0})
    total_expenses = Decimal("0")
    total_revenue = Decimal("0")
    dates: list[str] = []

    for b in bookings:
        month_key = b.document_date.strftime("%Y-%m")

        expense_key = expense_breakout_account(
            b.account, b.contra_account, exp_ranges, rev_ranges
        )
        revenue_key = revenue_breakout_account(
            b.account, b.contra_account, exp_ranges, rev_ranges,
            chart=client.chart_of_accounts,
        )
        is_expense = expense_key is not None
        is_revenue = revenue_key is not None

        if is_expense:
            monthly_map[month_key]["expenses"] += b.amount
            total_expenses += b.amount
            account_totals[expense_key] += b.amount

        if is_revenue:
            monthly_map[month_key]["revenue"] += b.amount
            total_revenue += b.amount
            account_totals[revenue_key] += b.amount

        if b.booking_text and is_expense:
            vendor_name = b.booking_text.strip()[:40]
            vendor_data[vendor_name]["total"] += b.amount
            vendor_data[vendor_name]["count"] += 1

        dates.append(month_key)

    monthly = sorted(
        [
            MonthlyAmount(month=m, expenses=d["expenses"], revenue=d["revenue"])
            for m, d in monthly_map.items()
        ],
        key=lambda x: x.month,
    )

    sorted_accounts = sorted(account_totals.items(), key=lambda x: x[1], reverse=True)[:10]
    accounts = [
        AccountBreakdown(
            account=acct,
            label=_account_label(acct, client.industry, client.chart_of_accounts),
            total=total,
        )
        for acct, total in sorted_accounts
    ]

    sorted_vendors = sorted(vendor_data.items(), key=lambda x: x[1]["total"], reverse=True)[:10]
    vendors = [
        TopVendor(name=name, total=data["total"], count=data["count"])
        for name, data in sorted_vendors
    ]

    period_from = min(dates) if dates else ""
    period_to = max(dates) if dates else ""

    return FinancialDashboard(
        monthly=monthly,
        accounts=accounts,
        vendors=vendors,
        total_expenses=total_expenses,
        total_revenue=total_revenue,
        period_from=period_from,
        period_to=period_to,
    )


@router.get("/{client_id}/activity", response_model=list[ActivityEntry])
async def get_recent_activity(
    client_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[ActivityEntry]:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    booking_ids_subq = (
        select(Booking.id).where(Booking.client_id == client_id).subquery()
    )
    document_ids_subq = (
        select(Document.id).where(Document.client_id == client_id).subquery()
    )
    export_ids_subq = (
        select(ExportBatch.id)
        .where(ExportBatch.client_id == client_id)
        .subquery()
    )

    query = (
        select(AuditLog)
        .where(
            (
                (AuditLog.entity_type == "booking")
                & AuditLog.entity_id.in_(select(booking_ids_subq))
            )
            | (
                (AuditLog.entity_type == "document")
                & AuditLog.entity_id.in_(select(document_ids_subq))
            )
            | (
                (AuditLog.entity_type == "export_batch")
                & AuditLog.entity_id.in_(select(export_ids_subq))
            )
        )
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )

    result = await db.execute(query)
    logs = result.scalars().all()

    entries: list[ActivityEntry] = []
    for log in logs:
        entity_label = ENTITY_LABELS.get(log.entity_type, log.entity_type)
        action_label = ACTION_LABELS.get(log.action, log.action)
        performer = log.performed_by or "System"
        summary = f"{entity_label} {action_label} von {performer}"

        entries.append(
            ActivityEntry(
                id=log.id,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                action=log.action,
                performed_by=log.performed_by,
                created_at=log.created_at,
                summary=summary,
            )
        )

    return entries
