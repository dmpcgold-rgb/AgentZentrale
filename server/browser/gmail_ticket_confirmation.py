#!/usr/bin/env python3
"""Read-only WESTbahn ticket confirmation from a user-authorized Gmail IMAP inbox.

No booking, message deletion, mailbox mutation, credential logging, or raw
ticket numbers in output. Credentials must be provided via private environment.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from html import unescape
import imaplib
import json
import os
import re
import sys

TRUSTED_SENDER_DOMAIN = "westbahn.at"
MAILBOX_HOST = "imap.gmail.com"


def plain_text(message):
    chunks = []
    for part in message.walk():
        if part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() not in ("text/plain", "text/html"):
            continue
        try:
            value = part.get_content()
        except (UnicodeError, ValueError, LookupError):
            continue
        if not isinstance(value, str):
            continue
        if part.get_content_type() == "text/html":
            value = re.sub(r"<[^>]*>", " ", value)
            value = unescape(value)
        chunks.append(value)
    return " ".join(" ".join(chunks).split())[:250000]


def sender_trusted(message):
    addr = parseaddr(str(message.get("From", "")))[1].lower()
    return addr.endswith("@" + TRUSTED_SENDER_DOMAIN) and addr.count("@") == 1


def mail_date(message):
    try:
        stamp = parsedate_to_datetime(str(message.get("Date", "")))
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def match_ticket(message, expected_date, seat, train):
    """Conservative positive evidence; a failed match never proves no ticket."""
    if not sender_trusted(message):
        return False
    stamp = mail_date(message)
    if stamp is None:
        return False
    # Tickets may be booked in advance; month/day in mail is not enough
    # without a year-bounded receipt timestamp.
    mail_day = stamp.date()
    if not expected_date - timedelta(days=90) <= mail_day <= expected_date + timedelta(days=1):
        return False
    subject = str(message.get("Subject", ""))
    if not re.search(r"westbahn[- ]ticket|ihr westbahn.ticket|buchungsbestätigung", subject, re.I):
        return False
    text = plain_text(message)
    month_names = ("jan","feb","mär","apr","mai","jun","jul","aug","sep","okt","nov","dez")
    month = month_names[expected_date.month - 1]
    date_numeric = re.search(r"(?<!\d)0?%d[./-]0?%d[./-]%d(?!\d)" % (
        expected_date.day, expected_date.month, expected_date.year), text, re.I)
    date_short = re.search(r"(?<!\d)0?%d\s+%s(?:ember)?\b" % (expected_date.day, month), text, re.I)
    if not date_numeric and not date_short:
        return False
    if not re.search(r"\b18:22\b", text):
        return False
    if not re.search(r"\bZug\s*:?\s*%s\b" % re.escape(train), text, re.I):
        return False
    if not re.search(r"\bSitz\s*:?\s*%s\b" % re.escape(seat), text, re.I):
        return False
    if not re.search(r"(?:W\.?\s*Meidling|Wien\s+Meidling)", text, re.I):
        return False
    if not re.search(r"(?:Wr\.?\s*Neustadt|Wiener\s+Neustadt)", text, re.I):
        return False
    if not re.search(r"2\+\s*\|?\s*Reservierung\s+Comfort\s+Class|Reservierung\s+Comfort\s+Class", text, re.I):
        return False
    has_pdf = any(p.get_content_disposition() == "attachment"
        and p.get_content_type() == "application/pdf"
        and str(p.get_filename() or "").lower().endswith(".pdf")
        for p in message.walk())
    has_ticket_reference = bool(re.search(
        r"\bTicket\s*(?:Nummer|Nr\.?)\b|/ticketshop/ticket/index/tno/", text, re.I))
    return has_pdf or has_ticket_reference


def confirm_from_gmail(expected_date, seat, train, *, max_messages=35):
    user = os.environ.get("WESTBAHN_GMAIL_ADDRESS", "").strip()
    secret = os.environ.get("WESTBAHN_GMAIL_APP_PASSWORD", "").replace(" ", "")
    if not user or not secret:
        return {"status": "email_not_configured", "ticketConfirmed": False,
                "bookingAuthorized": False}
    if not re.fullmatch(r"[\w.+-]+@gmail\.com", user, re.I):
        return {"status": "email_invalid_configuration", "ticketConfirmed": False,
                "bookingAuthorized": False}
    # Gmail IMAP uses TLS; no server-selected IMAP host override.
    try:
        with imaplib.IMAP4_SSL(MAILBOX_HOST, 993, timeout=18) as mail:
            mail.login(user, secret)
            ok, _ = mail.select("INBOX", readonly=True)
            if ok != "OK":
                return {"status": "email_read_unavailable", "ticketConfirmed": False,
                        "bookingAuthorized": False}
            after = (expected_date - timedelta(days=90)).strftime("%d-%b-%Y")
            ok, result = mail.uid("SEARCH", None, "SINCE", after)
            if ok != "OK" or not result:
                return {"status": "email_read_unavailable", "ticketConfirmed": False,
                        "bookingAuthorized": False}
            uids = result[0].split()[-max_messages:]
            for uid in reversed(uids):
                ok, rows = mail.uid("FETCH", uid, "(BODY.PEEK[])")
                if ok != "OK":
                    continue
                raw = next((row[1] for row in rows if isinstance(row, tuple)
                            and len(row) == 2 and isinstance(row[1], bytes)), None)
                if not raw:
                    continue
                message = BytesParser(policy=policy.default).parsebytes(raw)
                if match_ticket(message, expected_date, seat, train):
                    return {"status": "confirmed_by_westbahn_email",
                            "ticketConfirmed": True, "bookingAuthorized": False,
                            "confirmationSource": "official_email",
                            "date": expected_date.isoformat(), "train": train, "seat": seat}
            return {"status": "email_confirmation_not_found",
                    "ticketConfirmed": False, "bookingAuthorized": False,
                    "mailboxComplete": False}
    except (imaplib.IMAP4.error, OSError, TimeoutError, ValueError):
        return {"status": "email_read_unavailable", "ticketConfirmed": False,
                "bookingAuthorized": False}


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--date", required=True)
    cli.add_argument("--seat", required=True)
    cli.add_argument("--train", default="1009")
    args = cli.parse_args()
    try:
        day = date.fromisoformat(args.date)
        if not re.fullmatch(r"\d{2,4}[A-Z]", args.seat, re.I):
            raise ValueError()
        if not re.fullmatch(r"\d{1,5}", args.train):
            raise ValueError()
        output = confirm_from_gmail(day, args.seat.upper(), args.train)
    except ValueError:
        output = {"status": "invalid_confirmation_query",
                  "ticketConfirmed": False, "bookingAuthorized": False}
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
