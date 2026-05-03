"""IBAN/BIC/bank-name matching utilities for bank account resolution.

Pure functions with no database or LLM dependencies — easily testable.
"""

import re
from dataclasses import dataclass

from app.models.bank_account import BankAccount


def normalize_iban(raw: str) -> str:
    return raw.replace(" ", "").replace("-", "").upper()


def validate_iban_checksum(iban: str) -> bool:
    """ISO 7064 Mod 97-10 check."""
    if len(iban) < 5:
        return False
    rearranged = iban[4:] + iban[:4]
    numeric = ""
    for ch in rearranged:
        if ch.isdigit():
            numeric += ch
        elif ch.isalpha():
            numeric += str(ord(ch.upper()) - 55)
        else:
            return False
    try:
        return int(numeric) % 97 == 1
    except ValueError:
        return False


def iban_distance(a: str, b: str) -> int:
    """Character-level Hamming distance between two IBANs of equal length."""
    if len(a) != len(b):
        return max(len(a), len(b))
    return sum(1 for x, y in zip(a, b) if x != y)


_LEGAL_SUFFIXES = (" ag", " gmbh", " kg", " e.g.", " se", " co.", " & co")


def normalize_bank_name(name: str) -> str:
    n = name.lower().strip()
    for suffix in _LEGAL_SUFFIXES:
        n = n.replace(suffix, "")
    return re.sub(r"\s+", " ", n).strip()


BANK_NAME_ALIASES: dict[str, list[str]] = {
    "deutsche bank": ["dt. bank", "deutsche bk", "dtbank"],
    "commerzbank": ["commerzbk", "cbk", "commerzb."],
    "sparkasse": ["spk", "ksk", "kreissparkasse", "stadtsparkasse"],
    "volksbank": ["vr bank", "raiffeisenbank", "vr-bank", "voba"],
    "ing": ["ing-diba", "ing diba"],
    "unicredit": ["hypovereinsbank", "hvb"],
    "postbank": ["deutsche postbank", "pb"],
    "dkb": ["deutsche kreditbank"],
    "n26": ["n26 bank"],
    "targobank": ["targo"],
    "consorsbank": ["bnp paribas"],
}


def bank_names_match(name_a: str, name_b: str) -> bool:
    a = normalize_bank_name(name_a)
    b = normalize_bank_name(name_b)

    if a == b:
        return True
    if a in b or b in a:
        return True

    for canonical, aliases in BANK_NAME_ALIASES.items():
        all_names = [canonical, *aliases]
        a_match = any(alias in a for alias in all_names)
        b_match = any(alias in b for alias in all_names)
        if a_match and b_match:
            return True

    return False


# ---------------------------------------------------------------------------
# Matching strategies — each returns None / tuple on no-match
# ---------------------------------------------------------------------------


@dataclass
class MatchResult:
    account: BankAccount
    method: str
    confidence: float
    needs_review: bool = False
    reasoning: str = ""


def try_iban_exact(accounts: list[BankAccount], iban: str) -> MatchResult | None:
    normalized = normalize_iban(iban)
    for acc in accounts:
        if acc.iban and normalize_iban(acc.iban) == normalized:
            return MatchResult(
                account=acc,
                method="iban_exact",
                confidence=0.99,
                reasoning=f"IBAN {normalized} stimmt exakt mit Konto {acc.account_number} überein",
            )
    return None


def try_iban_fuzzy(
    accounts: list[BankAccount], iban: str, max_distance: int = 2
) -> MatchResult | None:
    normalized = normalize_iban(iban)
    best_acc: BankAccount | None = None
    best_dist = max_distance + 1

    for acc in accounts:
        if not acc.iban:
            continue
        acc_iban = normalize_iban(acc.iban)
        if len(acc_iban) != len(normalized):
            continue
        dist = iban_distance(normalized, acc_iban)
        if dist <= max_distance and dist < best_dist:
            best_dist = dist
            best_acc = acc

    if best_acc is None:
        return None

    conf = 0.85 if best_dist == 1 else 0.70
    if not validate_iban_checksum(normalized) and best_acc.iban:
        if validate_iban_checksum(normalize_iban(best_acc.iban)):
            conf += 0.05

    return MatchResult(
        account=best_acc,
        method="iban_fuzzy",
        confidence=conf,
        needs_review=best_dist > 1,
        reasoning=(
            f"IBAN {normalized} weicht um {best_dist} Zeichen von "
            f"{normalize_iban(best_acc.iban)} ab (Konto {best_acc.account_number}). "
            f"OCR-Fehler wahrscheinlich."
        ),
    )


def try_bic(accounts: list[BankAccount], bic: str) -> MatchResult | None:
    if not bic:
        return None
    normalized = bic.replace(" ", "").upper()
    for acc in accounts:
        if acc.bic and acc.bic.replace(" ", "").upper() == normalized:
            return MatchResult(
                account=acc,
                method="bic_match",
                confidence=0.80,
                reasoning=f"BIC {bic} matched Konto {acc.account_number}",
            )
    return None


def try_bank_name(
    accounts: list[BankAccount], bank_name: str
) -> list[BankAccount]:
    if not bank_name:
        return []
    return [acc for acc in accounts if bank_names_match(bank_name, acc.bank_name)]


def get_default_account(accounts: list[BankAccount]) -> BankAccount | None:
    for acc in accounts:
        if acc.is_default:
            return acc
    return None


def next_account_number(existing: list[BankAccount], chart: str) -> str:
    """Determine next available bank ledger account (e.g. 1210, 1220)."""
    base = 1200 if chart.upper() == "SKR03" else 1800
    step = 10
    used = {int(a.account_number) for a in existing if a.account_number.isdigit()}
    candidate = base
    while candidate in used:
        candidate += step
    return str(candidate)
