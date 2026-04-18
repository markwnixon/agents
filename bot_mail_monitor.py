#!/usr/bin/env python3
from __future__ import annotations

import argparse
import email
import imaplib
import os
import smtplib
import ssl
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from email.header import decode_header, make_header
from email.utils import parseaddr
from typing import Optional


@dataclass
class MailAccount:
    alias: str
    email_address: str
    imap_host: str
    imap_port: int
    imap_user: str
    imap_pass: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str


def env_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing environment variable: {name}")
    return value


def get_env_prefix() -> str:
    """
    Default to MAIL. Can be overridden with MAIL_ENV_PREFIX.
    Example:
        MAIL_ENV_PREFIX=MAIL
    """
    return os.getenv("MAIL_ENV_PREFIX", "MAIL").strip().upper()


def get_default_alias(prefix: str) -> str:
    """
    Looks for:
        MAIL_DEFAULT
    """
    return os.getenv(f"{prefix}_DEFAULT", "").strip()


def build_env_name(prefix: str, alias: str, field: str) -> str:
    """
    Example:
        prefix = MAIL
        alias  = quotes
        field  = IMAP_HOST

        -> MAIL_QUOTES_IMAP_HOST
    """
    return f"{prefix}_{alias.upper()}_{field}"


def load_account(alias: Optional[str]) -> MailAccount:
    prefix = get_env_prefix()
    selected = (alias or get_default_alias(prefix)).strip()

    if not selected:
        raise ValueError(
            f"No account alias provided and {prefix}_DEFAULT is not set."
        )

    return MailAccount(
        alias=selected,
        email_address=env_required(build_env_name(prefix, selected, "EMAIL")),
        imap_host=env_required(build_env_name(prefix, selected, "IMAP_HOST")),
        imap_port=int(env_required(build_env_name(prefix, selected, "IMAP_PORT"))),
        imap_user=env_required(build_env_name(prefix, selected, "IMAP_USER")),
        imap_pass=env_required(build_env_name(prefix, selected, "IMAP_PASS")),
        smtp_host=env_required(build_env_name(prefix, selected, "SMTP_HOST")),
        smtp_port=int(env_required(build_env_name(prefix, selected, "SMTP_PORT"))),
        smtp_user=env_required(build_env_name(prefix, selected, "SMTP_USER")),
        smtp_pass=env_required(build_env_name(prefix, selected, "SMTP_PASS")),
    )


def decode_mime(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def connect_imap(account: MailAccount) -> imaplib.IMAP4_SSL:
    client = imaplib.IMAP4_SSL(account.imap_host, account.imap_port)
    client.login(account.imap_user, account.imap_pass)
    client.select("INBOX")
    return client


def list_unread(account: MailAccount, limit: int) -> int:
    client = connect_imap(account)
    try:
        status, data = client.uid("search", None, "UNSEEN")
        if status != "OK":
            print("ERROR: Unable to search unread messages.", file=sys.stderr)
            return 1

        uids = [u.decode("utf-8") for u in data[0].split() if u]
        uids = uids[-limit:]

        print(f"Mailbox: {account.alias}")
        print(f"Email: {account.email_address}")
        print("")

        if not uids:
            print("Unread: 0")
            return 0

        print(f"Unread shown: {len(uids)}")
        print("")

        for uid in reversed(uids):
            status, msg_data = client.uid("fetch", uid, "(RFC822.HEADER)")
            if status != "OK" or not msg_data or not msg_data[0]:
                print(f"UID {uid}: <fetch error>")
                continue

            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            from_name, from_addr = parseaddr(msg.get("From", ""))
            from_display = decode_mime(from_name) or from_addr
            subject = decode_mime(msg.get("Subject", ""))
            date = msg.get("Date", "")

            print(f"UID: {uid}")
            print(f"From: {from_display} <{from_addr}>")
            print(f"Subject: {subject}")
            print(f"Date: {date}")
            print("-" * 60)

        return 0
    finally:
        try:
            client.close()
        except Exception:
            pass
        client.logout()


def html_to_text(html: str) -> str:
    import re
    text = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", "", html)
    text = re.sub(r"(?i)<br\\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?s)<.*?>", "", text)
    text = (
        text.replace("&nbsp;", " ")
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
    )
    return text.strip()


def extract_text_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition.lower():
                continue
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                if payload:
                    return payload.decode(charset, errors="replace")

        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                if payload:
                    return html_to_text(payload.decode(charset, errors="replace"))

        return ""

    payload = msg.get_payload(decode=True)
    charset = msg.get_content_charset() or "utf-8"
    if payload:
        return payload.decode(charset, errors="replace")
    return ""


def read_message(account: MailAccount, uid: str) -> int:
    client = connect_imap(account)
    try:
        status, msg_data = client.uid("fetch", uid, "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            print(f"ERROR: Unable to fetch UID {uid}.", file=sys.stderr)
            return 1

        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        print(f"Mailbox: {account.alias}")
        print(f"UID: {uid}")
        print(f"From: {decode_mime(msg.get('From', ''))}")
        print(f"To: {decode_mime(msg.get('To', ''))}")
        print(f"Subject: {decode_mime(msg.get('Subject', ''))}")
        print(f"Date: {msg.get('Date', '')}")
        print("")
        print(extract_text_body(msg))
        return 0
    finally:
        try:
            client.close()
        except Exception:
            pass
        client.logout()


def send_message(account: MailAccount, to_addr: str, subject: str, body_text: str) -> int:
    msg = EmailMessage()
    msg["From"] = account.email_address
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body_text)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(account.smtp_host, account.smtp_port, context=context) as server:
        server.login(account.smtp_user, account.smtp_pass)
        server.send_message(msg)

    print("Send status: success")
    print(f"Mailbox: {account.alias}")
    print(f"From: {account.email_address}")
    print(f"To: {to_addr}")
    print(f"Subject: {subject}")
    return 0


def show_config(account: MailAccount) -> int:
    """
    Safe debug output. Does not print passwords.
    """
    print(f"Mailbox alias: {account.alias}")
    print(f"Email       : {account.email_address}")
    print(f"IMAP host   : {account.imap_host}")
    print(f"IMAP port   : {account.imap_port}")
    print(f"IMAP user   : {account.imap_user}")
    print(f"SMTP host   : {account.smtp_host}")
    print(f"SMTP port   : {account.smtp_port}")
    print(f"SMTP user   : {account.smtp_user}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generic mail monitor helper.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List unread messages.")
    p_list.add_argument("--account", help="Mailbox alias, e.g. quotes or dispatch")
    p_list.add_argument("--limit", type=int, default=10)

    p_read = sub.add_parser("read", help="Read a message by UID.")
    p_read.add_argument("--account", help="Mailbox alias, e.g. quotes or dispatch")
    p_read.add_argument("--uid", required=True)

    p_send = sub.add_parser("send", help="Send a message.")
    p_send.add_argument("--account", help="Mailbox alias, e.g. quotes or dispatch")
    p_send.add_argument("--to", required=True)
    p_send.add_argument("--subject", required=True)
    group = p_send.add_mutually_exclusive_group(required=True)
    group.add_argument("--body")
    group.add_argument("--body-file")

    p_config = sub.add_parser("config", help="Show safe config details for a mailbox.")
    p_config.add_argument("--account", help="Mailbox alias, e.g. quotes or dispatch")

    args = parser.parse_args()

    try:
        account = load_account(getattr(args, "account", None))

        if args.command == "list":
            return list_unread(account, args.limit)

        if args.command == "read":
            return read_message(account, args.uid)

        if args.command == "send":
            body = args.body
            if args.body_file:
                with open(args.body_file, "r", encoding="utf-8") as f:
                    body = f.read()
            return send_message(account, args.to, args.subject, body or "")

        if args.command == "config":
            return show_config(account)

        print("Unknown command.", file=sys.stderr)
        return 1

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())