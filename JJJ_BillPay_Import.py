import csv
import datetime
import hashlib
import os
import socket
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from utils import getpaths


try:
    scac = sys.argv[1]
except Exception:
    scac = "oslm"

try:
    mode = sys.argv[2]
except Exception:
    mode = "review"

try:
    input_name = sys.argv[3]
except Exception:
    input_name = None

try:
    statement_pay_account_name = sys.argv[4]
except Exception:
    statement_pay_account_name = None

try:
    nt = sys.argv[5]
except Exception:
    nt = "remote"

scac = scac.upper()
mode = mode.lower()
host_name = socket.gethostname()
sys.path.append(getpaths(host_name, "system"))

os.environ["SCAC"] = scac
os.environ["PURPOSE"] = "script"
os.environ["MACHINE"] = host_name
os.environ["TUNNEL"] = nt

from remote_db_connect import db

if nt == "remote":
    from remote_db_connect import tunnel

from models8 import Accounts, Bills, Gledger, People


BASE_DIR = Path(__file__).resolve().parent / "incoming" / "billpay"
INBOX_DIR = BASE_DIR / "inbox"
REVIEW_DIR = BASE_DIR / "review"
PROCESSED_DIR = BASE_DIR / "processed"
ERROR_DIR = BASE_DIR / "error"
EXPENSE_TYPES = ["Expense", "Cost of Goods Sold", "Other Expense"]
PAYMENT_TYPES = ["Bank", "Credit Card", "Exch"]
AUTO_SKIP_PAYEES = ["GUSTO"]
GENERIC_VENDOR_WORDS = {
    "inc", "llc", "co", "corp", "corporation", "company", "logistics",
    "transport", "transportation", "services", "service", "the", "and",
}

HEADER_ALIASES = {
    "date": ["date", "transaction date", "posted date", "post date", "bill date", "payment date"],
    "vendor": ["vendor", "vendor name", "payee", "merchant", "name", "company", "description"],
    "description": ["description", "memo", "details", "line item", "transaction", "name"],
    "amount": ["amount", "transaction amount", "paid", "payment", "withdrawal", "debit"],
    "running_balance": ["running bal.", "running bal", "running balance", "balance"],
    "debit": ["debit", "withdrawal", "paid out", "charge"],
    "credit": ["credit", "deposit", "paid in"],
    "ref": ["ref", "reference", "check", "check number", "transaction id", "id"],
    "pay_account": ["account", "bank account", "paid from", "payment account"],
}
REQUIRED_TRANSACTION_FIELDS = ["date", "description", "amount"]


def clean_text(value, limit=None):
    cleaned = " ".join(str(value or "").strip().split())
    if limit:
        return cleaned[:limit]
    return cleaned


def retry_db(operation, label):
    last_error = None
    for attempt in range(1, 4):
        try:
            return operation()
        except OperationalError as exc:
            last_error = exc
            print(f"Database connection lost during {label}; reconnecting try {attempt}/3")
            try:
                db.session.rollback()
            except Exception:
                pass
            try:
                db.engine.dispose()
            except Exception:
                pass
    raise last_error


def account_snapshot(account):
    if account is None:
        return None
    return SimpleNamespace(
        id=account.id,
        Name=account.Name,
        Co=account.Co,
        Type=account.Type,
        Category=account.Category,
        Subcategory=account.Subcategory,
    )


def vendor_snapshot(vendor):
    if vendor is None:
        return None
    return SimpleNamespace(id=vendor.id, Company=vendor.Company)


def key_text(value, limit):
    return clean_text(value, limit).lower()


def money_decimal(value):
    try:
        if value is None:
            return Decimal("0.00")
        if isinstance(value, (int, float, Decimal)):
            return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cleaned = str(value).replace("$", "").replace(",", "").replace("(", "-").replace(")", "").strip()
        if cleaned in ["", "-", "None", "none"]:
            return Decimal("0.00")
        return Decimal(cleaned).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def cents_value(value):
    try:
        return int((Decimal(str(value)) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return 0


def numeric_decimal(value):
    try:
        if value is None:
            return None
        if isinstance(value, (int, float, Decimal)):
            return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cleaned = str(value).replace("$", "").replace(",", "").replace("(", "-").replace(")", "").strip()
        if cleaned in ["", "-", "None", "none"]:
            return None
        return Decimal(cleaned).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def parse_date(value):
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime.combine(value, datetime.time.min)
    text_value = clean_text(value)
    if not text_value:
        return None
    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"]:
        try:
            return datetime.datetime.strptime(text_value, fmt)
        except Exception:
            pass
    return None


def ensure_financial_import_tables():
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS financial_import_rules (
            id INT AUTO_INCREMENT PRIMARY KEY,
            Scac VARCHAR(20) NOT NULL,
            RuleType VARCHAR(30) NOT NULL DEFAULT 'bill',
            SourceType VARCHAR(30) NOT NULL DEFAULT '',
            VendorKey VARCHAR(200) NOT NULL DEFAULT '',
            DescriptionKey VARCHAR(250) NOT NULL DEFAULT '',
            VendorId INT,
            VendorName VARCHAR(100),
            ExpenseAccountId INT,
            ExpenseAccountName VARCHAR(50),
            PayAccountId INT,
            PayAccountName VARCHAR(50),
            IncomeAccountId INT,
            IncomeAccountName VARCHAR(50),
            Co VARCHAR(9),
            AccountType VARCHAR(45),
            AccountCategory VARCHAR(45),
            AccountSubcategory VARCHAR(45),
            Confidence DECIMAL(5,2) NOT NULL DEFAULT 1.00,
            MatchCount INT NOT NULL DEFAULT 0,
            LastUsedAt DATETIME,
            CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_financial_import_rule (
                Scac,
                RuleType,
                SourceType,
                VendorKey,
                DescriptionKey,
                Co
            ),
            INDEX idx_financial_import_rules_scac (Scac),
            INDEX idx_financial_import_rules_vendor (Scac, VendorKey),
            INDEX idx_financial_import_rules_expense (ExpenseAccountId)
        )
    """))
    existing_rule_columns = {
        row[0] for row in db.session.execute(text("SHOW COLUMNS FROM financial_import_rules"))
    }
    if "VendorId" not in existing_rule_columns:
        db.session.execute(text("ALTER TABLE financial_import_rules ADD COLUMN VendorId INT AFTER DescriptionKey"))
    db.session.commit()


def normalize_header(value):
    return clean_text(value).lower().replace("_", " ")


def header_map(headers):
    normalized = {normalize_header(header): index for index, header in enumerate(headers)}
    mapped = {}
    for field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapped[field] = normalized[alias]
                break
    return mapped


def header_score(mapped):
    score = 0
    for field in REQUIRED_TRANSACTION_FIELDS:
        if field in mapped:
            score += 2
    if "vendor" in mapped:
        score += 1
    if "debit" in mapped or "credit" in mapped:
        score += 1
    return score


def find_transaction_header(rows):
    best_index = None
    best_mapped = {}
    best_score = 0
    for index, row in enumerate(rows[:75]):
        headers = [clean_text(value) for value in row]
        mapped = header_map(headers)
        score = header_score(mapped)
        if score > best_score:
            best_index = index
            best_mapped = mapped
            best_score = score
    if best_score >= 5:
        return best_index, best_mapped
    return None, {}


def row_value(row, mapped, field):
    index = mapped.get(field)
    if index is None or index >= len(row):
        return None
    return row[index]


def amounts_match(previous_balance, amount, running_balance):
    if previous_balance is None or amount is None or running_balance is None:
        return False
    return abs((previous_balance + amount) - running_balance) <= Decimal("0.02")


def transaction_numbers(row, mapped, previous_balance):
    amount_index = mapped.get("amount")
    running_index = mapped.get("running_balance")

    if amount_index is not None:
        amount = numeric_decimal(row[amount_index] if amount_index < len(row) else None)
        running_balance = None
        if running_index is not None and running_index < len(row):
            running_balance = numeric_decimal(row[running_index])
        elif amount_index + 1 < len(row):
            running_balance = numeric_decimal(row[amount_index + 1])
        if amount is not None and (previous_balance is None or amounts_match(previous_balance, amount, running_balance)):
            return amount, running_balance, amount_index

    numeric_cells = []
    for index in range(2, len(row)):
        value = numeric_decimal(row[index])
        if value is not None:
            numeric_cells.append((index, value))

    for pos in range(len(numeric_cells) - 1):
        amount_index, amount = numeric_cells[pos]
        balance_index, running_balance = numeric_cells[pos + 1]
        if balance_index == amount_index + 1 and amounts_match(previous_balance, amount, running_balance):
            return amount, running_balance, amount_index

    if len(numeric_cells) == 1:
        index, running_balance = numeric_cells[0]
        if previous_balance is None:
            return None, running_balance, index

    if amount_index is not None and running_index is not None and running_index < len(row):
        running_balance = numeric_decimal(row[running_index])
        if running_balance is not None and previous_balance is None:
            return None, running_balance, amount_index

    return None, None, None


def row_description(row, mapped, amount_index):
    start = mapped.get("description", mapped.get("vendor", 1))
    stop = amount_index if amount_index is not None else len(row)
    pieces = []
    for index in range(start, min(stop, len(row))):
        value = clean_text(row[index])
        if value:
            pieces.append(value)
    return clean_text(" ".join(pieces), 600)


def load_xlsx(path):
    import openpyxl

    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []
    header_index, mapped = find_transaction_header(rows)
    if header_index is None:
        print(f"Could not find transaction table headers in {path.name}")
        return []
    print(f"Using transaction header row {header_index + 1} in {path.name}")
    return normalize_rows(path, rows[header_index + 1:], mapped, start_line=header_index + 2)


def load_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        rows = list(reader)
    if not rows:
        return []
    header_index, mapped = find_transaction_header(rows)
    if header_index is None:
        print(f"Could not find transaction table headers in {path.name}")
        return []
    print(f"Using transaction header row {header_index + 1} in {path.name}")
    return normalize_rows(path, rows[header_index + 1:], mapped, start_line=header_index + 2)


def normalize_rows(path, rows, mapped, start_line=2):
    items = []
    previous_balance = None
    missed_transaction_rows = 0
    for line_number, row in enumerate(rows, start=start_line):
        if not any(clean_text(value) for value in row):
            missed_transaction_rows += 1
            if previous_balance is not None and missed_transaction_rows >= 5:
                break
            continue
        transaction_date = parse_date(row_value(row, mapped, "date"))
        if transaction_date is None:
            missed_transaction_rows += 1
            if previous_balance is not None and missed_transaction_rows >= 5:
                break
            continue
        signed_amount, running_balance, amount_index = transaction_numbers(row, mapped, previous_balance)
        if signed_amount is None:
            if running_balance is not None:
                previous_balance = running_balance
            missed_transaction_rows += 1
            if previous_balance is not None and missed_transaction_rows >= 5:
                break
            continue
        missed_transaction_rows = 0
        amount = abs(signed_amount)
        record_type = "bill_payment" if signed_amount < 0 else "income"
        if amount == Decimal("0.00"):
            if running_balance is not None:
                previous_balance = running_balance
            continue
        vendor = clean_text(row_value(row, mapped, "vendor"), 100)
        description = row_description(row, mapped, amount_index)
        if not vendor:
            vendor = description[:100]
        if not description and not vendor:
            if running_balance is not None:
                previous_balance = running_balance
            continue
        ref = clean_text(row_value(row, mapped, "ref"), 50)
        pay_account = clean_text(row_value(row, mapped, "pay_account"), 50)
        import_key = hashlib.sha256(
            "|".join([
                scac,
                path.name,
                str(line_number),
                vendor,
                description,
                str(amount),
                transaction_date.strftime("%Y-%m-%d") if transaction_date else "",
                ref,
            ]).encode("utf-8")
        ).hexdigest()
        items.append({
            "source_file": path.name,
            "line_number": line_number,
            "vendor_name": vendor,
            "description": description,
            "amount": amount,
            "date": transaction_date,
            "ref": ref,
            "pay_account_name": pay_account,
            "import_key": import_key,
            "record_type": record_type,
        })
        if running_balance is not None:
            previous_balance = running_balance
    return items


def input_files():
    if input_name:
        path = Path(input_name)
        if not path.is_absolute():
            path = INBOX_DIR / input_name
        return [path]
    return sorted(
        path for path in INBOX_DIR.iterdir()
        if path.suffix.lower() in [".xlsx", ".xlsm", ".csv"]
    )


def load_file(path):
    if path.suffix.lower() in [".xlsx", ".xlsm"]:
        return load_xlsx(path)
    if path.suffix.lower() == ".csv":
        return load_csv(path)
    return []


def find_payment_account_by_name(account_name, company_code=None):
    account_name = clean_text(account_name, 50)
    if not account_name:
        return None
    query = Accounts.query.filter(
        (Accounts.Name == account_name) &
        (Accounts.Type.in_(PAYMENT_TYPES))
    )
    if company_code:
        query = query.filter(Accounts.Co == company_code)
    return retry_db(lambda: query.first(), "payment account lookup")


def infer_statement_payment_account(files):
    tokens = []
    for path in files:
        stem = path.stem
        token = ""
        for char in stem:
            if char.isdigit():
                token += char
            else:
                if len(token) >= 4:
                    tokens.append(token)
                token = ""
        if len(token) >= 4:
            tokens.append(token)
    if not tokens:
        return None
    accounts = retry_db(
        lambda: Accounts.query.filter(Accounts.Type.in_(PAYMENT_TYPES)).all(),
        "statement payment account inference",
    )
    matches = []
    for token in tokens:
        last4 = token[-4:]
        for account in accounts:
            acct_number = clean_text(account.AcctNumber)
            account_name = clean_text(account.Name)
            if acct_number.endswith(last4) or last4 in account_name:
                matches.append(account)
    unique = []
    seen = set()
    for account in matches:
        if account.id not in seen:
            unique.append(account)
            seen.add(account.id)
    return unique[0] if len(unique) == 1 else None


def vendor_options():
    return retry_db(
        lambda: People.query.filter(People.Ptype == "Vendor").order_by(People.Company).all(),
        "vendor list lookup",
    )


def normalize_match_text(value):
    text_value = "".join(ch.lower() if ch.isalnum() else " " for ch in (value or ""))
    return " ".join(text_value.split())


def likely_payee_text(item):
    text_value = clean_text(item.get("description") or item.get("vendor_name") or "")
    upper_value = text_value.upper()
    for marker in [" DES:", " ID:", " INDN:", " CO ID:", " DEBIT CARD", " PURCHASE "]:
        pos = upper_value.find(marker)
        if pos > 0:
            return text_value[:pos]
    return text_value


def should_auto_skip_item(item):
    payee_text = likely_payee_text(item).upper()
    description_text = clean_text(item.get("description")).upper()
    for payee in AUTO_SKIP_PAYEES:
        if payee in payee_text or description_text.startswith(payee):
            return True, payee
    return False, None


def suggested_vendor(item):
    payee_text = normalize_match_text(likely_payee_text(item))
    tx_text = normalize_match_text(" ".join([
        item.get("vendor_name") or "",
        item.get("description") or "",
    ]))
    best_vendor = None
    best_score = 0
    for vendor in vendor_options():
        vendor_text = normalize_match_text(vendor.Company)
        if not vendor_text:
            continue
        vendor_words = [
            word for word in vendor_text.split()
            if len(word) >= 4 and word not in GENERIC_VENDOR_WORDS
        ]
        matched_words = [word for word in vendor_words if word in payee_text]
        if vendor_text in payee_text:
            score = len(vendor_text)
        elif len(vendor_words) == 1 and matched_words:
            score = len(matched_words[0])
        elif len(matched_words) >= 2:
            score = sum(len(word) for word in matched_words)
        else:
            score = 0
        if score > best_score:
            best_vendor = vendor
            best_score = score
    return best_vendor if best_score >= 5 else None


def choose_vendor(prompt, current_vendor=None):
    options = vendor_options()
    if not options:
        print("No vendor options found in People where Ptype = Vendor.")
        return None
    for index, vendor in enumerate(options, start=1):
        marker = " *" if current_vendor is not None and vendor.id == current_vendor.id else ""
        print(f"{index:>3}. {vendor.Company}{marker}")
    while True:
        choice = input(prompt).strip()
        if choice.lower() in ["", "l", "later", "skip"]:
            return current_vendor
        try:
            return options[int(choice) - 1]
        except Exception:
            print("Enter a vendor number, or blank to keep the current vendor.")


def existing_bill_matches(item, pay_account=None, company_code=None):
    if item.get("record_type") != "bill_payment" or item.get("date") is None:
        return []
    amount = abs(item["amount"])
    start = item["date"] - datetime.timedelta(days=10)
    end = item["date"] + datetime.timedelta(days=10)
    query = Bills.query.filter(Bills.pDate >= start).filter(Bills.pDate <= end)
    if company_code:
        query = query.filter(Bills.Co == company_code)
    if pay_account is not None:
        query = query.filter(Bills.pAccount == pay_account.Name)
    rows = retry_db(
        lambda: query.order_by(Bills.pDate.desc(), Bills.id.desc()).limit(200).all(),
        "existing bill payment lookup",
    )
    rows = [
        bill for bill in rows
        if bill.Status == "Paid" and money_decimal(bill.pAmount) == amount
    ][:20]
    tx_day = item["date"].date()
    return sorted(
        rows,
        key=lambda bill: (
            abs(((bill.pDate.date() if isinstance(bill.pDate, datetime.datetime) else bill.pDate) - tx_day).days)
            if bill.pDate else 9999,
            -(bill.id or 0),
        )
    )


def existing_transfer_matches(item, pay_account=None, company_code=None):
    if item.get("record_type") != "bill_payment" or item.get("date") is None or pay_account is None:
        return []
    amount_cents = cents_value(abs(item["amount"]))
    start = item["date"] - datetime.timedelta(days=10)
    end = item["date"] + datetime.timedelta(days=10)
    credit_rows = retry_db(
        lambda: Gledger.query.filter(
            (Gledger.Type == "XC") &
            (Gledger.Account == pay_account.Name) &
            (Gledger.Credit == amount_cents) &
            (Gledger.Date >= start) &
            (Gledger.Date <= end)
        ).order_by(Gledger.Date.desc(), Gledger.id.desc()).limit(50).all(),
        "existing transfer credit lookup",
    )
    matches = []
    tx_day = item["date"].date()
    for credit in credit_rows:
        if company_code and credit.Com != company_code:
            continue
        debit = retry_db(
            lambda: Gledger.query.filter(
                (Gledger.Tcode == credit.Tcode) &
                (Gledger.Type == "XD") &
                (Gledger.Debit == amount_cents)
            ).first(),
            "existing transfer debit lookup",
        )
        if debit is not None:
            matches.append((credit, debit))
    return sorted(
        matches,
        key=lambda match: (
            abs(((match[0].Date.date() if isinstance(match[0].Date, datetime.datetime) else match[0].Date) - tx_day).days)
            if match[0].Date else 9999,
            -(match[0].id or 0),
        )
    )


def existing_rule(item, company_code):
    vendor_key = key_text(item["vendor_name"], 200)
    description_key = key_text(item["description"], 250)
    return retry_db(
        lambda: db.session.execute(
            text("""
                SELECT *
                FROM financial_import_rules
                WHERE Scac = :scac
                  AND RuleType = 'bill'
                  AND (:co = '' OR Co = :co)
                  AND (
                        (VendorKey = :vendor_key AND DescriptionKey = :description_key)
                     OR (VendorKey = :vendor_key AND DescriptionKey = '')
                     OR VendorKey = :vendor_key
                  )
                ORDER BY
                    CASE
                        WHEN VendorKey = :vendor_key AND DescriptionKey = :description_key THEN 1
                        WHEN VendorKey = :vendor_key AND DescriptionKey = '' THEN 2
                        ELSE 3
                    END,
                    MatchCount DESC,
                    LastUsedAt DESC
                LIMIT 1
            """),
            {
                "scac": scac,
                "co": company_code or "",
                "vendor_key": vendor_key,
                "description_key": description_key,
            },
        ).mappings().first(),
        "financial import rule lookup",
    )


def history_suggestion(item, company_code):
    amount = f"{abs(item['amount']):.2f}"
    query = Bills.query.filter(Bills.bAmount == amount)
    if company_code:
        query = query.filter(Bills.Co == company_code)
    if item["vendor_name"]:
        query = query.filter(Bills.Company.contains(item["vendor_name"][:30]))
    bill = retry_db(
        lambda: query.order_by(Bills.Date.desc(), Bills.id.desc()).first(),
        "bill history amount/vendor lookup",
    )
    if bill is None and item["vendor_name"]:
        query = Bills.query.filter(Bills.Company.contains(item["vendor_name"][:30]))
        if company_code:
            query = query.filter(Bills.Co == company_code)
        bill = retry_db(
            lambda: query.order_by(Bills.Date.desc(), Bills.id.desc()).first(),
            "bill history vendor lookup",
        )
    if bill is None:
        return None
    expense = find_expense_account_for_bill(bill)
    pay = retry_db(
        lambda: Accounts.query.filter((Accounts.Name == bill.pAccount) & (Accounts.Co == bill.Co)).first(),
        "bill history payment account lookup",
    )
    return {
        "source": "bill history",
        "expense": expense,
        "pay": pay,
        "co": bill.Co,
        "bill": bill,
    }


def rule_suggestion(item, company_code):
    rule = existing_rule(item, company_code)
    if rule is None:
        return None
    expense = retry_db(lambda: Accounts.query.get(rule["ExpenseAccountId"]), "rule expense account lookup") if rule["ExpenseAccountId"] else None
    pay = retry_db(lambda: Accounts.query.get(rule["PayAccountId"]), "rule payment account lookup") if rule["PayAccountId"] else None
    return {
        "source": "learned rule",
        "expense": expense,
        "pay": pay,
        "co": rule["Co"],
        "rule": rule,
    }


def account_options(company_code, types):
    query = Accounts.query.filter(Accounts.Type.in_(types))
    if company_code:
        query = query.filter(Accounts.Co == company_code)
    return retry_db(
        lambda: query.order_by(Accounts.Co, Accounts.Category, Accounts.Name).all(),
        "account options lookup",
    )


def choose_account(prompt, company_code, types):
    options = account_options(company_code, types)
    if not options:
        print(f"No account options found for {company_code or 'all companies'}")
        return None
    for index, account in enumerate(options, start=1):
        print(f"{index:>3}. {account.Co} | {account.Name} | {account.Type} | {account.Category} | {account.Subcategory}")
    while True:
        choice = input(prompt).strip()
        if choice.lower() in ["", "l", "later", "skip"]:
            return None
        try:
            selected = options[int(choice) - 1]
            return selected
        except Exception:
            print("Enter an account number, or blank to skip.")


def first_payment_account(company_code):
    return retry_db(
        lambda: Accounts.query.filter(
            (Accounts.Type.in_(PAYMENT_TYPES)) &
            (Accounts.Co == company_code)
        ).order_by(Accounts.Type, Accounts.Name).first(),
        "default payment account lookup",
    )


def find_expense_account_for_bill(bill):
    if bill is None:
        return None
    exact = retry_db(
        lambda: Accounts.query.filter((Accounts.Name == bill.bAccount) & (Accounts.Co == bill.Co)).first(),
        "matched bill exact expense account lookup",
    )
    if exact is not None:
        return exact

    bill_account_text = normalize_match_text(bill.bAccount)
    accounts = retry_db(
        lambda: Accounts.query.filter(
            (Accounts.Co == bill.Co) &
            (Accounts.Type.in_(EXPENSE_TYPES))
        ).all(),
        "matched bill fallback expense account lookup",
    )
    contained_matches = []
    for account in accounts:
        account_text = normalize_match_text(account.Name)
        if bill_account_text and (bill_account_text in account_text or account_text in bill_account_text):
            contained_matches.append(account)
    if len(contained_matches) == 1:
        return contained_matches[0]

    metadata_matches = [
        account for account in accounts
        if account.Type == bill.bType
        and account.Category == bill.bCat
        and account.Subcategory == bill.bSubcat
    ]
    if len(metadata_matches) == 1:
        return metadata_matches[0]
    return None


def save_rule(item, vendor, expense_account, pay_account, company_code):
    now = datetime.datetime.now()
    params = {
        "scac": scac,
        "source_type": "spreadsheet_review",
        "vendor_key": key_text(item["vendor_name"], 200),
        "description_key": key_text(item["description"], 250),
        "vendor_id": vendor.id if vendor is not None else None,
        "vendor_name": clean_text(vendor.Company if vendor is not None else item["vendor_name"], 100),
        "expense_account_id": expense_account.id,
        "expense_account_name": expense_account.Name,
        "pay_account_id": pay_account.id if pay_account is not None else None,
        "pay_account_name": pay_account.Name if pay_account is not None else None,
        "co": company_code,
        "account_type": expense_account.Type,
        "account_category": expense_account.Category,
        "account_subcategory": expense_account.Subcategory,
        "now": now,
    }
    def write_rule():
        db.session.execute(
            text("""
                INSERT INTO financial_import_rules
                    (Scac, RuleType, SourceType, VendorKey, DescriptionKey,
                     VendorId, VendorName, ExpenseAccountId, ExpenseAccountName,
                     PayAccountId, PayAccountName, Co, AccountType,
                     AccountCategory, AccountSubcategory, MatchCount,
                     LastUsedAt, CreatedAt, UpdatedAt)
                VALUES
                    (:scac, 'bill', :source_type, :vendor_key, :description_key,
                     :vendor_id, :vendor_name, :expense_account_id, :expense_account_name,
                     :pay_account_id, :pay_account_name, :co, :account_type,
                     :account_category, :account_subcategory, 1, :now, :now, :now)
                ON DUPLICATE KEY UPDATE
                    VendorId = VALUES(VendorId),
                    VendorName = VALUES(VendorName),
                    ExpenseAccountId = VALUES(ExpenseAccountId),
                    ExpenseAccountName = VALUES(ExpenseAccountName),
                    PayAccountId = VALUES(PayAccountId),
                    PayAccountName = VALUES(PayAccountName),
                    AccountType = VALUES(AccountType),
                    AccountCategory = VALUES(AccountCategory),
                    AccountSubcategory = VALUES(AccountSubcategory),
                    MatchCount = MatchCount + 1,
                    LastUsedAt = VALUES(LastUsedAt),
                    UpdatedAt = VALUES(UpdatedAt)
            """),
            params,
        )
        db.session.commit()
        return True

    return retry_db(write_rule, "financial import rule save")


def auto_save_match_rule(item, matches, vendor, expense, pay):
    if not matches or vendor is None or expense is None or pay is None:
        return False
    if pay.Co != expense.Co:
        return False
    save_rule(item, vendor, expense, pay, expense.Co)
    match = matches[0]
    pdate = match.pDate.strftime("%Y-%m-%d") if match.pDate else ""
    print(
        f"Auto-saved line {item['line_number']} from existing bill "
        f"{match.Jo} | {match.Company} | {pdate} | ${match.pAmount} | {match.bAccount}"
    )
    return True


def review_item(item, default_company_code, statement_pay_account=None, auto_accept_matches=False):
    if item["record_type"] != "bill_payment":
        print(f"Skipping income/deposit line {item['line_number']}: {item['vendor_name']} {item['amount']}")
        return "skipped"
    auto_skip, skip_name = should_auto_skip_item(item)
    if auto_skip:
        print(f"Skipping {skip_name} payroll line {item['line_number']}: {item['amount']} {item['description'][:80]}")
        return "skipped"

    pay = statement_pay_account
    if pay is None:
        pay = find_payment_account_by_name(item.get("pay_account_name"), default_company_code)
    company_code = pay.Co if pay is not None else default_company_code

    transfer_matches = existing_transfer_matches(item, pay, company_code)
    if transfer_matches:
        credit, debit = transfer_matches[0]
        tdate = credit.Date.strftime("%Y-%m-%d") if credit.Date else ""
        print(
            f"Skipping account transfer line {item['line_number']}: "
            f"{credit.Tcode} | {tdate} | ${item['amount']} | "
            f"{credit.Account} -> {debit.Account}"
        )
        return "transfer"

    matches = existing_bill_matches(item, pay, company_code)
    suggestion = None
    vendor = None
    expense = None
    if matches:
        suggestion = {"source": "existing paid bill date/account/amount match", "bill": matches[0]}
        vendor = retry_db(lambda: People.query.get(matches[0].Pid), "matched bill vendor lookup") if matches[0].Pid else None
        expense = find_expense_account_for_bill(matches[0])
        matched_pay = retry_db(
            lambda: Accounts.query.filter((Accounts.Name == matches[0].pAccount) & (Accounts.Co == matches[0].Co)).first(),
            "matched bill payment account lookup",
        )
        pay = account_snapshot(matched_pay) or pay
        company_code = matches[0].Co or company_code
    else:
        suggestion = rule_suggestion(item, company_code) or history_suggestion(item, company_code)
        expense = suggestion["expense"] if suggestion else None
        if pay is None and suggestion:
            pay = suggestion["pay"]
        if suggestion and suggestion.get("co"):
            company_code = suggestion["co"]
        if expense is not None:
            company_code = expense.Co

    if vendor is None and suggestion and suggestion.get("rule") is not None and suggestion["rule"].get("VendorId"):
        vendor = retry_db(lambda: People.query.get(suggestion["rule"]["VendorId"]), "rule vendor lookup")
    if vendor is None:
        vendor = suggested_vendor(item)

    if auto_accept_matches and auto_save_match_rule(item, matches, vendor, expense, pay):
        return "auto_saved"

    print("")
    print("_______________________________________________________")
    print(f"File: {item['source_file']} line {item['line_number']}")
    print(f"Date: {item['date'].strftime('%Y-%m-%d') if item['date'] else 'Unknown'}")
    print(f"Statement text/vendor: {item['vendor_name']}")
    print(f"Description: {item['description']}")
    print(f"Amount: {item['amount']}")
    if matches:
        print("Already in bill payments: YES")
        for index, bill in enumerate(matches[:5], start=1):
            pdate = bill.pDate.strftime('%Y-%m-%d') if bill.pDate else ''
            print(f"  {index}. {bill.Jo} | {bill.Company} | {pdate} | ${bill.pAmount} | {bill.pAccount} | {bill.bAccount}")
    else:
        print("Already in bill payments: No date/account/amount match found")
    if suggestion:
        print(f"Suggestion source: {suggestion['source']}")
    if vendor is not None:
        print(f"Vendor selection: {vendor.Company}")
    else:
        print("Vendor selection: No suggestion")
    if expense is not None:
        print(f"Expense category: {expense.Co} | {expense.Name} | {expense.Category} | {expense.Subcategory}")
    else:
        print("Expense category: No suggestion")
    if pay is not None:
        print(f"Payment account: {pay.Co} | {pay.Name}")
    else:
        print("Payment account: No suggestion")

    while True:
        answer = input("[A]ccept rule, [V]endor, [C]ategory, [P]ayment account, [L]ater, [Q]uit: ").strip().lower()
        if answer in ["a", "accept"]:
            if vendor is None:
                print("There is no vendor selected. Choose a vendor before saving the rule.")
                continue
            if expense is None:
                print("There is no expense category to accept.")
                continue
            if pay is not None and pay.Co != expense.Co:
                print("Payment account company does not match expense category company.")
                continue
            save_rule(item, vendor, expense, pay, expense.Co)
            print("Rule saved.")
            return "saved"
        if answer in ["v", "vendor"]:
            vendor = vendor_snapshot(choose_vendor("Choose vendor number: ", vendor))
        elif answer in ["c", "choose", "category"]:
            expense = account_snapshot(choose_account("Choose expense account number: ", company_code, EXPENSE_TYPES))
            if expense is not None:
                company_code = expense.Co
                if pay is not None and pay.Co != company_code:
                    pay = first_payment_account(company_code)
        elif answer in ["p", "payment"]:
            pay = account_snapshot(choose_account("Choose payment account number: ", company_code, PAYMENT_TYPES))
        elif answer in ["l", "later", "skip", ""]:
            print("Marked for later; no rule saved.")
            return "later"
        elif answer in ["q", "quit"]:
            raise KeyboardInterrupt
        else:
            print("Choose A, V, C, P, L, or Q.")


def review_mode(auto_accept_matches=False):
    ensure_financial_import_tables()
    for folder in [INBOX_DIR, REVIEW_DIR, PROCESSED_DIR, ERROR_DIR]:
        folder.mkdir(parents=True, exist_ok=True)
    files = input_files()
    if not files:
        print(f"No spreadsheet files found in {INBOX_DIR}")
        return
    statement_pay_account = find_payment_account_by_name(statement_pay_account_name)
    if statement_pay_account_name and statement_pay_account is None:
        print(f"Payment account '{statement_pay_account_name}' was not found.")
    if statement_pay_account is None:
        inferred_account = infer_statement_payment_account(files)
        if inferred_account is not None:
            answer = input(
                f"Use inferred statement payment account {inferred_account.Co} | {inferred_account.Name}? [Y/n]: "
            ).strip().lower()
            if answer in ["", "y", "yes"]:
                statement_pay_account = inferred_account
    if statement_pay_account is None:
        print("Choose the payment account for this statement.")
        statement_pay_account = choose_account("Choose payment account number: ", None, PAYMENT_TYPES)
    if statement_pay_account is None:
        print("No payment account selected. Review stopped before any rules were written.")
        return
    statement_pay_account = account_snapshot(statement_pay_account)
    default_company_code = statement_pay_account.Co
    print(f"Using statement payment account: {statement_pay_account.Co} | {statement_pay_account.Name}")
    saved = auto_saved = transfer_skipped = skipped = later = 0
    try:
        for path in files:
            if not path.exists():
                print(f"Missing file: {path}")
                continue
            print(f"Reviewing {path}")
            items = load_file(path)
            print(f"Found {len(items)} usable rows")
            for item in items:
                item["pay_account_name"] = statement_pay_account.Name
                outcome = review_item(
                    item,
                    default_company_code,
                    statement_pay_account,
                    auto_accept_matches=auto_accept_matches,
                )
                if outcome == "saved":
                    saved += 1
                elif outcome == "auto_saved":
                    auto_saved += 1
                elif outcome == "transfer":
                    transfer_skipped += 1
                elif outcome == "later":
                    later += 1
                else:
                    skipped += 1
    except KeyboardInterrupt:
        print("")
        print("Review stopped by user.")
    print(
        f"Review complete. Auto-saved: {auto_saved}; manually saved: {saved}; "
        f"transfers skipped: {transfer_skipped}; marked later: {later}; skipped: {skipped}"
    )


if __name__ == "__main__":
    print(f"Running JJJ_BillPay_Import for {scac} in {mode} mode using tunnel mode: {nt}")
    if mode == "review":
        review_mode()
    elif mode in ["auto", "review-auto", "autoreview"]:
        review_mode(auto_accept_matches=True)
    elif mode in ["ensure", "setup"]:
        ensure_financial_import_tables()
        print("Financial import tables are ready.")
    else:
        print("Only review/setup modes are enabled. No API posting is available from this agent yet.")
    if nt == "remote":
        tunnel.stop()
