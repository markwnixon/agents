#!/usr/bin/env python3
"""
Mail monitor for First Eagle Logistics job orders.

Usage examples:
  python3 scripts/mail_monitor.py scan               # Scan INBOX for new matches (stateful)
  python3 scripts/mail_monitor.py audit --folder "INBOX.Work Orders"  # Evaluate detection on training folder
"""
from __future__ import annotations

import argparse
import email
import imaplib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.header import decode_header
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_PATH = BASE_DIR / "state" / "mail_monitor.json"
LOG_PATH = BASE_DIR / "state" / "work_order_moves.log"
DEFAULT_FOLDER = "INBOX"
TRAINING_FOLDER = '"INBOX.Work Orders"'  

def env_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing environment variable: {name}")
    return value


def get_mail_env_prefix() -> str:
    return os.getenv("MAIL_ENV_PREFIX", "MAIL").strip().upper()


def get_default_alias(prefix: str) -> str:
    return os.getenv(f"{prefix}_DEFAULT", "").strip()


def build_mail_env_name(prefix: str, alias: str, field: str) -> str:
    return f"{prefix}_{alias.upper()}_{field}"

SUBJECT_KEYWORDS = [
    "delivery order",
    "rate con",
    "rate confirmation",
    "rate confermation",
    "notice of arrival",
    "booking",
    "load #",
    "load#",
    "drop & pick",
    "drayage",
    "seagirt",
    "eta",
    "ref#",
    "ref:",
    "pos.:",
    "order",
]
ATTACHMENT_KEYWORDS = [
    "delivery",
    "do",
    "rate",
    "rc",
    "booking",
    "order",
    "notice",
    "dray",
    "pod",
]
TRUSTED_SENDERS = [
    "@expresschb.com",
    "@immensitylogistics.com",
    "@profreight.us",
    "@vablogistics.com",
    "@friendshiplogistics.com",
    "@bestbaylogistics.com",
    "@netchb.com",
    "@efreightship.com",
    "@digilogistixandfreights.com",
    "@kartash.com",
    "@onesourceamerica.com",
    "@absolutewl.com",
    "@firsteaglelogistics.com",
]
BODY_KEYWORDS = [
    "delivery order",
    "rate con",
    "rate confirmation",
    "drop & pick",
    "drayage",
    "eta",
    "container",
    "bill of lading",
]

CONTAINER_REGEX = re.compile(r"\b([A-Z]{4}\d{7})\b")
BOOKING_REGEXES = [
    re.compile(r"\bBKG[#\s:-]*([A-Z0-9]{5,})", re.IGNORECASE),
    re.compile(r"\bBOOKING[#\s:-]*([A-Z0-9]{5,})", re.IGNORECASE),
    re.compile(r"\bBKNG[#\s:-]*([A-Z0-9]{5,})", re.IGNORECASE),
]

@dataclass
class MessageSummary:
    uid: int
    subject: str
    sender: str
    date: str
    attachments: List[Dict[str, str]]
    has_pdf: bool
    body_excerpt: str

@dataclass
class MailboxConfig:
    alias: str
    email: str
    imap_host: str
    imap_port: int
    imap_user: str
    imap_pass: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str


def load_mailbox_config(alias: Optional[str] = None) -> MailboxConfig:
    prefix = get_mail_env_prefix()
    selected = (alias or get_default_alias(prefix)).strip()
    if not selected:
        raise ValueError(f"No mailbox alias provided and {prefix}_DEFAULT is not set.")

    return MailboxConfig(
        alias=selected,
        email=env_required(build_mail_env_name(prefix, selected, "EMAIL")),
        imap_host=env_required(build_mail_env_name(prefix, selected, "IMAP_HOST")),
        imap_port=int(env_required(build_mail_env_name(prefix, selected, "IMAP_PORT"))),
        imap_user=env_required(build_mail_env_name(prefix, selected, "IMAP_USER")),
        imap_pass=env_required(build_mail_env_name(prefix, selected, "IMAP_PASS")),
        smtp_host=env_required(build_mail_env_name(prefix, selected, "SMTP_HOST")),
        smtp_port=int(env_required(build_mail_env_name(prefix, selected, "SMTP_PORT"))),
        smtp_user=env_required(build_mail_env_name(prefix, selected, "SMTP_USER")),
        smtp_pass=env_required(build_mail_env_name(prefix, selected, "SMTP_PASS")),
    )


def connect_imap(conf: MailboxConfig) -> imaplib.IMAP4_SSL:
    if not all([conf.imap_host, conf.imap_user, conf.imap_pass]):
        raise ValueError("Missing IMAP config values")

    client = imaplib.IMAP4_SSL(conf.imap_host, conf.imap_port)
    client.login(conf.imap_user, conf.imap_pass)
    return client


def decode_mime(value: Optional[str]) -> str:
    if not value:
        return ""
    result = ""
    for frag, enc in decode_header(value):
        if isinstance(frag, bytes):
            result += frag.decode(enc or "utf-8", errors="replace")
        else:
            result += frag
    return result


def extract_summary(raw_msg: bytes, uid: int) -> MessageSummary:
    msg = email.message_from_bytes(raw_msg)
    subject = decode_mime(msg.get("Subject")) or "(no subject)"
    sender = decode_mime(msg.get("From"))
    date = msg.get("Date", "")
    attachments: List[Dict[str, str]] = []
    body_chunks: List[str] = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        if filename:
            decoded_name = decode_mime(filename)
            payload = part.get_payload(decode=True) or b""
            attachments.append(
                {
                    "filename": decoded_name,
                    "content_type": part.get_content_type(),
                    "size": str(len(payload)),
                }
            )
        elif part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True) or b""
            try:
                text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            except LookupError:
                text = payload.decode("utf-8", errors="replace")
            body_chunks.append(text)
    has_pdf = any(att["filename"].lower().endswith(".pdf") for att in attachments)
    body_excerpt = "\n".join(body_chunks)[:2000]
    return MessageSummary(
        uid=uid,
        subject=subject,
        sender=sender,
        date=date,
        attachments=attachments,
        has_pdf=has_pdf,
        body_excerpt=body_excerpt,
    )


def sender_score(sender: str) -> int:
    sender_lower = sender.lower()
    return 1 if any(domain in sender_lower for domain in TRUSTED_SENDERS) else 0


def keyword_hits(text: str, keywords: Iterable[str]) -> int:
    lowered = text.lower()
    hits = 0
    for kw in keywords:
        if kw in lowered:
            hits += 1
    return hits


def attachment_score(attachments: List[Dict[str, str]]) -> int:
    score = 0
    if attachments:
        score += 1
    if any(att["filename"].lower().endswith(".pdf") for att in attachments):
        score += 1
    if any(
        any(token in att["filename"].lower() for token in ATTACHMENT_KEYWORDS)
        for att in attachments
    ):
        score += 1
    return score

def has_reference_number(summary: MessageSummary) -> bool:
    text = f"{summary.subject}\n{summary.body_excerpt}".upper()
    if CONTAINER_REGEX.search(text):
        return True
    for pattern in BOOKING_REGEXES:
        if pattern.search(text):
            return True
    return False


def classify(summary: MessageSummary) -> Tuple[bool, int, Dict[str, int]]:
    has_ref = has_reference_number(summary)
    metrics = {
        "subject_hits": keyword_hits(summary.subject, SUBJECT_KEYWORDS),
        "body_hits": keyword_hits(summary.body_excerpt, BODY_KEYWORDS),
        "sender": sender_score(summary.sender),
        "attachments": attachment_score(summary.attachments),
        "pdf": 1 if summary.has_pdf else 0,
        "reference": 1 if has_ref else 0,
    }
    score = metrics["subject_hits"] * 2 + metrics["body_hits"] + metrics["sender"] + metrics["attachments"]
    is_match = summary.has_pdf and has_ref and score >= 4
    return is_match, score, metrics


def load_state() -> Dict[str, int]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            pass
    return {"last_uid": 0}


def save_state(state: Dict[str, int]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


def fetch_uids(client: imaplib.IMAP4_SSL, since_uid: int = 0, folder: str = DEFAULT_FOLDER) -> List[int]:
    status, _ = client.select(folder)
    if status != "OK":
        raise RuntimeError(f"Unable to select folder {folder}")
    if since_uid:
        criteria = f"UID {since_uid + 1}:*"
        status, data = client.uid("search", None, criteria)
    else:
        status, data = client.uid("search", None, "ALL")
    if status != "OK":
        raise RuntimeError("UID search failed")
    uids = [int(x) for x in data[0].split()]
    return uids


def fetch_message_by_uid(client: imaplib.IMAP4_SSL, uid: int) -> bytes:
    status, data = client.uid("fetch", str(uid), "(RFC822)")
    if status != "OK" or not data or not isinstance(data[0], tuple):
        raise RuntimeError(f"Failed to fetch UID {uid}")
    return data[0][1]


def cmd_scan(args: argparse.Namespace) -> None:
    conf = load_mailbox_config(getattr(args, "account", None))
    state = load_state()
    last_uid = state.get("last_uid", 0)
    with connect_imap(conf) as client:
        uids = fetch_uids(client, since_uid=last_uid, folder=DEFAULT_FOLDER)
        if not uids:
            print("No new messages to evaluate.")
            return
        matches: List[Dict[str, object]] = []
        for uid in uids:
            raw = fetch_message_by_uid(client, uid)
            summary = extract_summary(raw, uid)
            is_match, score, metrics = classify(summary)
            status_str = "MATCH" if is_match else "skip"
            print(f"[{status_str}] UID {uid} | {summary.date} | {summary.subject}")
            if is_match:
                matches.append(
                    {
                        "uid": uid,
                        "subject": summary.subject,
                        "sender": summary.sender,
                        "date": summary.date,
                        "score": score,
                        "metrics": metrics,
                        "attachments": summary.attachments,
                    }
                )
                if args.move_folder:
                    move_to_folder(client, uid, args.move_folder)
                    log_move(summary, score, metrics, args.move_folder)
        state["last_uid"] = max(uids)
        save_state(state)
        if matches:
            print("\nSummary of detected work orders:")
            for item in matches:
                print(f" - UID {item['uid']} | score {item['score']} | {item['subject']}")
        else:
            print("No work-order candidates detected this run.")


def move_to_folder(client: imaplib.IMAP4_SSL, uid: int, folder: str) -> None:
    status, _ = client.uid("copy", str(uid), folder)
    if status == "OK":
        client.uid("store", str(uid), "+FLAGS", "(\\Deleted)")
        client.expunge()
        print(f"   moved UID {uid} to {folder}")
    else:
        print(f"   WARN: copy to {folder} failed ({status})")


def log_move(summary: MessageSummary, score: int, metrics: Dict[str, int], folder: str) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uid": summary.uid,
        "folder": folder,
        "subject": summary.subject,
        "sender": summary.sender,
        "score": score,
        "metrics": metrics,
    }
    with LOG_PATH.open("a") as handle:
        handle.write(json.dumps(entry) + "\n")


def cmd_audit(args: argparse.Namespace) -> None:
    conf = load_mailbox_config(getattr(args, "account", None))
    folder = args.folder
    with connect_imap(conf) as client:
        if folder.lower() == "work_orders":
            folder_name = TRAINING_FOLDER
        elif folder.startswith("INBOX"):
            folder_name = folder
        else:
            folder_name = f'"{folder}"'
        uids = fetch_uids(client, since_uid=0, folder=folder_name)
        if not uids:
            print(f"Folder {folder_name} is empty")
            return
        hits = 0
        for uid in uids:
            raw = fetch_message_by_uid(client, uid)
            summary = extract_summary(raw, uid)
            is_match, score, metrics = classify(summary)
            if is_match:
                hits += 1
            status_str = "MATCH" if is_match else "MISS "
            print(f"[{status_str}] UID {uid} score={score} subject={summary.subject}")
        accuracy = hits / len(uids)
        print(f"\nDetected {hits}/{len(uids)} messages (accuracy {accuracy:.1%})")


def cmd_backfill(args: argparse.Namespace) -> None:
    conf = load_mailbox_config(getattr(args, "account", None))
    since_date = datetime.strptime(args.since_date, "%Y-%m-%d").date()
    imap_date = since_date.strftime("%d-%b-%Y")
    move_target = args.move_folder or '"INBOX.Work Orders"'
    with connect_imap(conf) as client:
        status, _ = client.select(DEFAULT_FOLDER)
        if status != "OK":
            raise RuntimeError(f"Unable to select {DEFAULT_FOLDER}")
        status, data = client.uid("search", None, f"(SINCE {imap_date})")
        if status != "OK":
            raise RuntimeError("UID search with SINCE failed")
        uids = [int(x) for x in data[0].split()]
        if not uids:
            print("No messages found in the requested window.")
            return
        if args.limit:
            uids = uids[-args.limit:]
        total = len(uids)
        moved = 0
        for idx, uid in enumerate(uids, 1):
            raw = fetch_message_by_uid(client, uid)
            summary = extract_summary(raw, uid)
            is_match, score, metrics = classify(summary)
            status_str = "MATCH" if is_match else "skip"
            print(f"[{status_str}] {idx}/{total} UID {uid} | {summary.date} | {summary.subject}")
            if is_match:
                move_to_folder(client, uid, move_target)
                log_move(summary, score, metrics, move_target)
                moved += 1
        print(f"\nBackfill complete: moved {moved} of {total} messages into {move_target}.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect work-order emails via IMAP")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan INBOX for new work orders")
    scan.add_argument("--account", help="Mailbox alias, e.g. mnixon")
    scan.add_argument(
        "--move-folder",
        metavar="FOLDER",
        help="Optional IMAP folder to move positive matches into (e.g., \"INBOX.Work Orders\")",
        default=None,
    )
    scan.set_defaults(func=cmd_scan)

    audit = sub.add_parser("audit", help="Evaluate detection rules on a folder")
    audit.add_argument("--account", help="Mailbox alias, e.g. mnixon")
    audit.add_argument(
        "--folder",
        required=True,
        help="IMAP folder to audit (use Work_Orders to target INBOX.Work Orders)",
    )
    backfill = sub.add_parser("backfill", help="Move historical work-order mail since a date")
    backfill.add_argument("--account", help="Mailbox alias, e.g. mnixon")
    backfill.add_argument("--since-date", required=True, help="YYYY-MM-DD (inclusive)")
    backfill.add_argument(
        "--move-folder",
        default='"INBOX.Work Orders"',
        help="IMAP folder to copy matches into (default: INBOX.Work Orders)",
    )
    backfill.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only evaluate the most recent N messages within the time window",
    )
    backfill.set_defaults(func=cmd_backfill)

    audit.set_defaults(func=cmd_audit)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
