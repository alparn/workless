# Tax Localization Guide — Adapting Workless for International Tax Systems

> **Deutsche Zusammenfassung:** Workless verwendet Markdown-basierte „Skill-Dateien" in `backend/app/skills/`, um dem KI-Buchhalter länderspezifische Regeln beizubringen (Kontenrahmen, Steuerschlüssel, Absetzbarkeitsregeln). Um Workless für ein anderes Land anzupassen, erstellen Sie neue Skill-Dateien mit den jeweiligen Kontenrahmen, Steuersätzen und Vorschriften, und konfigurieren Sie den Mandanten entsprechend. Diese Anleitung erklärt das System und zeigt detaillierte Beispiele für die USA und Großbritannien.

---

## 1. Overview

Workless is an AI-powered accounting assistant that generates booking (journal entry) suggestions from uploaded invoices, receipts, and bank statements. The AI does not hard-code any accounting rules. Instead, it relies on **Markdown skill files** that describe:

- Which **chart of accounts** to use (account numbers, names, typical usage)
- Which **tax/VAT codes** to attach to postings
- **Tax deduction rules** (partial deductibility, thresholds, documentation requirements)
- **Document type classification** logic (invoice vs. receipt vs. credit note)
- **Bank account resolution** rules (mapping IBANs to ledger accounts)

These skill files are injected into the LLM prompt as context at inference time. The AI reads them, applies the rules, and produces jurisdiction-correct bookings. To support a new country, you replace or supplement these files — no code changes required.

### Current skill files (Germany)

| File | Purpose |
|------|---------|
| `skr03.md` | German chart of accounts SKR03 (top 40 accounts with usage guidance) |
| `skr04.md` | German chart of accounts SKR04 (alternative German chart of accounts) |
| `vat_keys.md` | DATEV BU-Schlüssel (posting keys) for automatic VAT splitting |
| `tax_deduction_rules.md` | German tax deduction rules (entertainment, gifts, low-value assets, depreciation, etc.) |
| `document_types.md` | Document classification decision tree |
| `bank_account_resolution.md` | IBAN-to-ledger-account matching logic |

---

## 2. Architecture

### How skill files are loaded

The loading mechanism is intentionally simple — a single function in `backend/app/services/skills.py`:

```python
from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"

def load_skill(filename: str) -> str:
    return (SKILLS_DIR / filename).read_text(encoding="utf-8")
```

### How skills flow into the LLM prompt

When the document processing pipeline reaches the **booking suggestion** node, the system:

1. Reads the client's `chart_of_accounts` setting (e.g., `"SKR03"`)
2. Calls `load_skill(f"{chart.lower()}.md")` to load the matching chart of accounts
3. Calls `load_skill("vat_keys.md")` to load the tax code reference
4. Queries the database for **dynamic skills** — client-specific rules learned from corrections, chat instructions, and clarifications
5. Assembles all of this into a single prompt sent to the LLM

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Skill Files │────▶│ Prompt Build │────▶│   LLM (Claude)   │
│  (Markdown)  │     │              │     │                  │
└─────────────┘     │  + OCR data   │     │  → Booking JSON  │
                    │  + Vendor hx  │     └──────────────────┘
┌─────────────┐     │  + Industry   │
│  Dynamic     │────▶│    context   │
│  Skills (DB) │     └──────────────┘
└─────────────┘
```

### Client configuration model

Each client stores jurisdiction-relevant settings in the database:

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `chart_of_accounts` | `String(10)` | `"SKR03"` | Determines which chart-of-accounts skill file to load |
| `default_vat_rate` | `Decimal(4,2)` | `19.00` | Default tax rate for the jurisdiction |
| `fiscal_year_start` | `Date` | `2026-01-01` | Start of the fiscal year |
| `account_length` | `Integer` | `4` | Number of digits in account numbers |

---

## 3. Adapting for the USA

### 3.1 Replace the chart of accounts

Create a new file `backend/app/skills/us_standard.md` with a US-style chart of accounts:

```markdown
# US Standard Chart of Accounts

You are an experienced US bookkeeper. Use the following accounts
to generate journal entry suggestions for US businesses.

## 1000–1999 — Assets

| Account | Name | Typical Use |
|---------|------|-------------|
| 1000 | Cash | Petty cash |
| 1010 | Checking Account | Primary business checking |
| 1020 | Savings Account | Business savings |
| 1100 | Accounts Receivable | Customer invoices outstanding |
| 1200 | Inventory | Goods held for resale |
| 1500 | Equipment | Computers, machinery (capitalize > $2,500) |
| 1510 | Furniture & Fixtures | Desks, chairs, shelving |
| 1520 | Vehicles | Company cars and trucks |
| 1600 | Accumulated Depreciation | Contra-asset for fixed assets |

## 2000–2999 — Liabilities

| Account | Name | Typical Use |
|---------|------|-------------|
| 2000 | Accounts Payable | Vendor bills outstanding |
| 2100 | Sales Tax Payable | Collected sales tax owed to state |
| 2200 | Payroll Liabilities | Withheld taxes and benefits |
| 2300 | Credit Card Payable | Business credit card balances |

## 3000–3999 — Equity

| Account | Name | Typical Use |
|---------|------|-------------|
| 3000 | Owner's Equity | Capital contributions |
| 3100 | Retained Earnings | Accumulated prior-year profits |

## 4000–4999 — Revenue

| Account | Name | Typical Use |
|---------|------|-------------|
| 4000 | Sales Revenue | Product or service sales |
| 4100 | Service Revenue | Revenue from services rendered |
| 4900 | Other Income | Interest, miscellaneous income |

## 5000–6999 — Expenses

| Account | Name | Typical Use |
|---------|------|-------------|
| 5000 | Cost of Goods Sold | Direct costs of products sold |
| 6000 | Rent Expense | Office or warehouse rent |
| 6100 | Utilities | Electricity, water, internet |
| 6200 | Office Supplies | Paper, toner, stationery |
| 6300 | Travel Expense | Flights, hotels, per diem |
| 6310 | Meals & Entertainment | Business meals (50% deductible) |
| 6400 | Advertising & Marketing | Ads, promotions, sponsorships |
| 6500 | Professional Fees | Legal, accounting, consulting |
| 6600 | Insurance | Business insurance premiums |
| 6700 | Depreciation Expense | Periodic depreciation charges |
| 6800 | Payroll Expense | Gross wages and salaries |
| 6900 | Miscellaneous Expense | Catch-all for minor expenses |

## Posting Rules

1. **Sales tax**: Collected from customers → credit 2100; remitted to state → debit 2100.
2. **Debit/Credit**: Expenses are debited, Revenue is credited.
3. **Amounts**: Always record gross amounts. Track sales tax separately.
4. **Descriptions**: Max 60 characters, format: "Vendor – Description"
```

### 3.2 Replace VAT keys with US sales tax codes

Create `backend/app/skills/us_sales_tax.md`:

```markdown
# US Sales Tax Reference

Unlike European VAT, US sales tax is imposed at the state and local level.
There is no federal sales tax. Rates vary by jurisdiction.

## Common State Rates (examples)

| State | Base Rate | Notes |
|-------|-----------|-------|
| California | 7.25% | Local additions can push total to ~10% |
| Texas | 6.25% | No state income tax |
| New York | 4.00% | NYC adds 4.5% local |
| Florida | 6.00% | No state income tax |
| Oregon | 0.00% | No sales tax |
| Delaware | 0.00% | No sales tax |

## Key Differences from German VAT

| Aspect | Germany (VAT) | USA (Sales Tax) |
|--------|---------------|-----------------|
| Level | Federal | State + local |
| Input tax credit | Yes (Vorsteuer) | No (not recoverable by buyer) |
| Shown on invoice | Required (net + VAT) | Total with tax line |
| Rate | 19% / 7% uniform | Varies by state/city |
| Filing | Monthly/quarterly USt-VA | Varies by state |

## Tax Exempt Transactions

- Sales to resellers (with valid resale certificate)
- Sales to tax-exempt organizations (501(c)(3) with exemption certificate)
- Most B2B services (varies by state)
- Interstate sales (economic nexus rules apply)

## Decision Guide

1. **Standard purchase** — Record full amount as expense, no tax split
2. **Taxable sale** — Record revenue + sales tax payable to 2100
3. **Tax-exempt sale** — Record revenue only, keep exemption certificate on file
4. **Use tax** — If vendor did not charge tax, accrue use tax to 2100
```

### 3.3 Adapt tax deduction rules to IRS rules

Create `backend/app/skills/us_tax_deduction_rules.md` covering key IRS provisions:

```markdown
# US Tax Deduction Rules — IRS Reference

You are an experienced US tax advisor. Check every journal entry for
deductibility and provide tax_hints accordingly.

## Meals & Entertainment (IRC §274)

| Criterion | Rule |
|-----------|------|
| Business meals | 50% deductible (must have business purpose) |
| Entertainment | 0% deductible (eliminated by TCJA 2017) |
| Employee meals (for convenience) | 50% deductible |
| Required documentation | Date, place, amount, business purpose, attendees |

## De Minimis Safe Harbor (Reg. §1.263(a)-1(f))

| Criterion | Rule |
|-----------|------|
| Threshold (with AFS) | Items ≤ $5,000 — expense immediately |
| Threshold (without AFS) | Items ≤ $2,500 — expense immediately |
| Election | Must make annual election on tax return |
| Applies to | Tangible property, not inventory |

## Section 179 Expensing (IRC §179)

| Criterion | Rule |
|-----------|------|
| Maximum deduction | $1,160,000 (2023, indexed annually) |
| Phase-out threshold | Begins at $2,890,000 in total acquisitions |
| Eligible property | Tangible personal property, off-the-shelf software, certain improvements |
| Not eligible | Real property (buildings), land |

## Bonus Depreciation (IRC §168(k))

| Criterion | Rule |
|-----------|------|
| 2023 rate | 80% first-year bonus depreciation |
| 2024 rate | 60% (phasing down 20% per year) |
| Eligible property | New and used property with recovery period ≤ 20 years |

## Business Gifts (IRC §274(b))

| Criterion | Rule |
|-----------|------|
| Limit | $25 per recipient per year |
| Incidental costs | Wrapping, shipping excluded from $25 limit |
| Required records | Recipient name, business relationship, cost |

## Home Office Deduction (IRC §280A)

| Criterion | Rule |
|-----------|------|
| Simplified method | $5/sq ft, max 300 sq ft ($1,500/year) |
| Actual method | Pro-rata share of mortgage, utilities, insurance, etc. |
| Requirement | Regular and exclusive use for business |

## Vehicle Expenses (IRC §274(d))

| Criterion | Rule |
|-----------|------|
| Standard mileage rate | $0.655/mile (2023) |
| Actual expense method | Depreciation + gas + insurance + maintenance × business % |
| Substantiation | Mileage log with date, destination, purpose, miles |
```

### 3.4 Adapt document types for US formats

Create `backend/app/skills/us_document_types.md` or extend `document_types.md`:

```markdown
# US Document Types — Additional Classifications

## W-9 — Request for Taxpayer Identification Number
- Collect from vendors/contractors before first payment
- Not a booking document; store for records
- Required before issuing 1099

## 1099-NEC — Nonemployee Compensation
- Issued to contractors paid ≥ $600/year
- Due to IRS by January 31
- Classify as: tax_form

## 1099-MISC — Miscellaneous Income
- Rents, prizes, other income ≥ $600
- Classify as: tax_form

## W-2 — Wage and Tax Statement
- Employee wage summary; classify as: tax_form

## Invoice (US format)
- No VAT line; may include sales tax as separate line
- Terms: Net 30, Net 60, Due on Receipt
- May include PO number
```

### 3.5 Export format

> **Important:** DATEV EXTF export is Germany-specific. For US clients, you would export to:
> - **CSV** — Generic import for QuickBooks, Xero, or other US accounting software
> - **QBO** (QuickBooks format) — OFX-based format
> - **IIF** (Intuit Interchange Format) — Legacy QuickBooks import

This requires implementing a new export service alongside the existing `datev_export.py`. The booking data model is format-agnostic — only the serialization layer changes.

---

## 4. Adapting for the UK

### 4.1 UK Chart of Accounts

Create `backend/app/skills/uk_standard.md` with accounts following common UK numbering:

| Range | Category | Example Accounts |
|-------|----------|-----------------|
| 0001–0999 | Fixed Assets | 0010 Freehold Property, 0030 Plant & Machinery, 0040 Motor Vehicles |
| 1000–1999 | Current Assets | 1100 Debtors (Trade), 1200 Bank Current Account, 1230 Petty Cash |
| 2000–2999 | Liabilities | 2100 Creditors (Trade), 2200 VAT Liability, 2300 PAYE/NI |
| 3000–3999 | Capital & Reserves | 3000 Share Capital, 3100 Retained Earnings |
| 4000–4999 | Sales | 4000 Sales (Standard Rate), 4010 Sales (Reduced Rate), 4020 Sales (Zero Rate) |
| 5000–5999 | Purchases | 5000 Cost of Sales, 5100 Purchases |
| 6000–7999 | Overheads | 6000 Rent, 6100 Insurance, 6200 Motor Expenses, 7000 Wages |
| 8000–8999 | Other Income | 8000 Interest Received |

### 4.2 UK VAT Rates

Create `backend/app/skills/uk_vat.md`:

| Rate | Value | Applies To |
|------|-------|------------|
| Standard | 20% | Most goods and services |
| Reduced | 5% | Children's car seats, energy-saving materials, sanitary products |
| Zero-rated | 0% | Food (most), children's clothing, books, newspapers |
| Exempt | N/A | Insurance, financial services, education, health |

VAT-registered businesses reclaim input VAT (similar to German Vorsteuer).

### 4.3 Making Tax Digital (MTD)

UK businesses must submit VAT returns digitally via HMRC-compatible software. For Workless to support UK clients:

- Export VAT data in MTD-compatible format
- Track the 9 VAT return boxes (Box 1–9)
- Support quarterly filing periods
- Integrate with HMRC's MTD API for direct submission (future)

---

## 5. Step-by-Step Guide: Creating Custom Skill Files

### Step 1 — Copy a template

Start with an existing German skill file as a structural template:

```bash
cp backend/app/skills/skr03.md backend/app/skills/us_standard.md
```

### Step 2 — Replace the content

Edit the new file with your jurisdiction's accounts, tax rules, and conventions. Follow the existing Markdown structure:

- Use tables for account listings
- Include a "Rules" section at the end with posting logic
- Write instructions in second person ("Use account 6310 for…")
- Include the role prompt at the top ("You are an experienced US bookkeeper…")

### Step 3 — Place in the skills directory

All skill files live in:

```
backend/app/skills/
├── skr03.md                    # Germany (existing)
├── skr04.md                    # Germany (existing)
├── vat_keys.md                 # Germany (existing)
├── tax_deduction_rules.md      # Germany (existing)
├── document_types.md           # Universal + Germany
├── bank_account_resolution.md  # Germany (existing)
├── us_standard.md              # USA (new)
├── us_sales_tax.md             # USA (new)
├── us_tax_deduction_rules.md   # USA (new)
├── uk_standard.md              # UK (new)
└── uk_vat.md                   # UK (new)
```

### Step 4 — Update `load_skill` calls

The booking suggestion node loads the chart of accounts dynamically based on the client's `chart_of_accounts` field:

```python
skr_skill = load_skill(f"{chart.lower()}.md")
```

So setting a client's `chart_of_accounts` to `"US_STANDARD"` will automatically load `us_standard.md`. No code changes needed for the chart of accounts.

For the VAT/tax code file, the current code hard-codes `load_skill("vat_keys.md")`. To support multiple jurisdictions, modify the prompt builder to select the tax code file based on the chart of accounts:

```python
TAX_CODE_MAP = {
    "SKR03": "vat_keys.md",
    "SKR04": "vat_keys.md",
    "US_STANDARD": "us_sales_tax.md",
    "UK_STANDARD": "uk_vat.md",
}

tax_skill = load_skill(TAX_CODE_MAP.get(chart, "vat_keys.md"))
```

### Step 5 — Configure the client

Update the client settings via the API or database:

```json
{
  "chart_of_accounts": "US_STANDARD",
  "default_vat_rate": 0.00,
  "fiscal_year_start": "2026-01-01",
  "account_length": 4
}
```

---

## 6. Client Configuration for International Use

The `Client` model already contains the fields needed for localization:

| Field | German Client | US Client | UK Client |
|-------|--------------|-----------|-----------|
| `chart_of_accounts` | `SKR03` or `SKR04` | `US_STANDARD` | `UK_STANDARD` |
| `default_vat_rate` | `19.00` | `0.00` (no federal sales tax) | `20.00` |
| `fiscal_year_start` | `2026-01-01` | `2026-01-01` (calendar year typical) | `2026-04-06` (UK tax year) |
| `account_length` | `4` | `4` | `4` |
| `datev_consultant_number` | Required | N/A | N/A |
| `datev_client_number` | Required | N/A | N/A |

### Suggested schema additions for full international support

| Field | Type | Purpose |
|-------|------|---------|
| `country_code` | `String(2)` | ISO 3166-1 alpha-2 (e.g., `DE`, `US`, `GB`) |
| `currency` | `String(3)` | ISO 4217 currency code (e.g., `EUR`, `USD`, `GBP`) |
| `tax_system` | `String(20)` | `"vat"`, `"sales_tax"`, `"gst"` |
| `export_format` | `String(20)` | `"datev"`, `"csv"`, `"qbo"`, `"mtd"` |

---

## 7. Future Roadmap

The skills-based architecture makes Workless inherently extensible. Planned enhancements:

### Country-specific skill packs

Bundle all skill files for a jurisdiction into a downloadable pack:

```
skill-packs/
├── de/
│   ├── skr03.md
│   ├── skr04.md
│   ├── vat_keys.md
│   └── tax_deduction_rules.md
├── us/
│   ├── us_standard.md
│   ├── us_sales_tax.md
│   └── us_tax_deduction_rules.md
└── gb/
    ├── uk_standard.md
    └── uk_vat.md
```

### Automatic skill selection based on client country

When a client's `country_code` is set, the system could automatically:
- Load the correct chart of accounts
- Apply the matching tax code reference
- Select jurisdiction-appropriate deduction rules
- Choose the correct export format

### Multi-currency support

- Store amounts with currency codes
- Apply exchange rates for cross-border transactions
- Handle currency gain/loss postings
- Support multi-currency bank accounts

### Country-specific export formats

| Country | Format | Standard |
|---------|--------|----------|
| Germany | DATEV EXTF | Already implemented |
| USA | CSV / QBO / IIF | QuickBooks, Xero compatible |
| UK | CSV / MTD JSON | HMRC Making Tax Digital |
| EU | SAF-T XML | Standard Audit File for Tax |
| France | FEC | Fichier des Écritures Comptables |

### Community-contributed skill files

Open-source contributors could submit skill files for their jurisdictions, reviewed by local tax professionals before inclusion.

---

## Appendix: Quick Reference

### Minimum files needed per jurisdiction

| # | File | Content |
|---|------|---------|
| 1 | Chart of accounts | Account numbers, names, categories, posting rules |
| 2 | Tax codes | Tax rates, codes, when to apply them |
| 3 | Deduction rules | Deductibility limits, documentation requirements, legal references |
| 4 | Document types | Country-specific document formats and classification logic |

### Checklist for adding a new country

- [ ] Create chart of accounts skill file
- [ ] Create tax code reference skill file
- [ ] Create tax deduction rules skill file
- [ ] Extend document types for local formats (optional)
- [ ] Adapt bank account resolution for local banking (optional)
- [ ] Add the `chart_of_accounts` value to `TAX_CODE_MAP`
- [ ] Test with sample invoices from the target country
- [ ] Verify deduction rules produce correct `tax_hints`
- [ ] Implement export format if DATEV is not applicable
