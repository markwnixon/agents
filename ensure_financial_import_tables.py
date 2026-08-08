import os
import socket
import sys

from sqlalchemy import text

from utils import getpaths


try:
    scac = sys.argv[1]
except Exception:
    scac = "oslm"

try:
    nt = sys.argv[2]
except Exception:
    nt = "remote"

scac = scac.upper()
host_name = socket.gethostname()
sys.path.append(getpaths(host_name, "system"))

os.environ["SCAC"] = scac
os.environ["PURPOSE"] = "script"
os.environ["MACHINE"] = host_name
os.environ["TUNNEL"] = nt

from remote_db_connect import db

if nt == "remote":
    from remote_db_connect import tunnel


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
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS financial_import_records (
            id INT AUTO_INCREMENT PRIMARY KEY,
            Scac VARCHAR(20) NOT NULL,
            ImportKey VARCHAR(128) NOT NULL,
            SourceFile VARCHAR(255),
            SourceType VARCHAR(30),
            LineNumber INT,
            RecordType VARCHAR(30),
            VendorName VARCHAR(100),
            Description VARCHAR(600),
            Amount VARCHAR(20),
            TransactionDate DATE,
            Ref VARCHAR(50),
            Status VARCHAR(30) NOT NULL DEFAULT 'new',
            BillId INT,
            PaymentId INT,
            LedgerJournalId VARCHAR(100),
            RuleId INT,
            ErrorText VARCHAR(1000),
            RawText TEXT,
            CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_financial_import_record (Scac, ImportKey),
            INDEX idx_financial_import_records_scac_status (Scac, Status),
            INDEX idx_financial_import_records_bill (BillId),
            INDEX idx_financial_import_records_rule (RuleId)
        )
    """))
    db.session.commit()


if __name__ == "__main__":
    print(f"Ensuring financial import tables for {scac} in tunnel mode: {nt}")
    ensure_financial_import_tables()
    print("Financial import tables are ready.")
    if nt == "remote":
        tunnel.stop()
