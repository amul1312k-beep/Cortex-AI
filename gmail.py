"""
Cortex AI — Gmail Module
Full email intelligence layer for Cortex AI. Built entirely on Python's
standard library (imaplib, smtplib, email) — zero pip installs required.

Capabilities:
  - Send, reply, forward — plain text, HTML, or with attachments
  - Read & search — recent, unread, Gmail-syntax search (X-GM-RAW)
  - Full message parsing — subject, sender, body, attachment list,
    correctly decodes MIME-encoded headers (emoji/unicode subjects etc.)
  - Flags — mark read/unread, star/unstar
  - Organize — archive, delete (Trash), custom labels, list labels
  - Drafts — save directly into Gmail's Drafts folder
  - Attachments — download to disk
  - Local sent-mail log (JSON) and inbox summary report
  - Connection self-test with clear setup guidance
  - Natural language command dispatcher

SETUP (one-time, ~2 minutes):
  1. Enable 2-Step Verification on your Google account:
     https://myaccount.google.com/security
  2. Generate an App Password:
     https://myaccount.google.com/apppasswords
  3. Create a file named `.env` in your Cortex AI folder with:
       GMAIL_ADDRESS=youraddress@gmail.com
       GMAIL_APP_PASSWORD=your16digitapppassword
     (No quotes, no spaces around the =)

That's it — no Google Cloud Console, no OAuth consent screen.
"""

import os
import re
import time
import json
import imaplib
import smtplib
import datetime
from email import message_from_bytes
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email import encoders

# ---------------------------------------------------------------------------
# Paths & Config
# ---------------------------------------------------------------------------

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DATA_DIR        = os.path.join(BASE_DIR, "data")
SENT_LOG        = os.path.join(DATA_DIR, "sent_emails_log.json")
ATTACHMENT_DIR  = os.path.join(os.path.expanduser("~"), "Downloads", "Cortex Email Attachments")

os.makedirs(DATA_DIR, exist_ok=True)

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

DRAFTS_FOLDER = '"[Gmail]/Drafts"'


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _respond(msg: str) -> str:
    print(f"  [GMAIL] {msg}")
    return msg


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_json(path: str, default):
    if not os.path.exists(path):
        _save_json(path, default)
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default


def _save_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _log_sent(to: str, subject: str) -> None:
    log = _load_json(SENT_LOG, [])
    log.insert(0, {"to": to, "subject": subject, "sent_at": _now()})
    _save_json(SENT_LOG, log[:100])


def _split_addresses(addr_string: str) -> list:
    """'a@x.com, b@x.com' -> ['a@x.com', 'b@x.com']"""
    return [a.strip() for a in addr_string.split(",") if a.strip()]


def _find_env_file() -> str:
    """Check same folder first, then one level up — works flat or nested."""
    for candidate in (os.path.join(BASE_DIR, ".env"), os.path.join(BASE_DIR, "..", ".env")):
        if os.path.exists(candidate):
            return candidate
    return os.path.join(BASE_DIR, ".env")


def _load_env_var(key: str) -> str:
    """Check OS environment first, then parse the .env file directly (no dotenv package needed)."""
    value = os.environ.get(key)
    if value:
        return value
    env_path = _find_env_file()
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _get_credentials() -> tuple:
    email_addr = _load_env_var("GMAIL_ADDRESS")
    password = _load_env_var("GMAIL_APP_PASSWORD")
    if not email_addr or not password:
        raise RuntimeError(
            "Gmail credentials not found. Add GMAIL_ADDRESS and GMAIL_APP_PASSWORD to your "
            ".env file. Generate an app password at https://myaccount.google.com/apppasswords "
            "(requires 2-Step Verification enabled first)."
        )
    return email_addr, password


def _decode_mime_header(value) -> str:
    """Decode MIME-encoded headers (e.g. '=?UTF-8?B?...?=') into readable text."""
    if not value:
        return ""
    result = ""
    for part, encoding in decode_header(value):
        if isinstance(part, bytes):
            result += part.decode(encoding or "utf-8", errors="ignore")
        else:
            result += part
    return result


def _parse_email(raw_bytes: bytes) -> dict:
    """Parse a raw RFC822 email into a clean dict — subject, sender, body, attachments."""
    msg = message_from_bytes(raw_bytes)
    body_text, body_html, attachments = "", "", []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))

            if "attachment" in disposition:
                filename = part.get_filename()
                if filename:
                    attachments.append(_decode_mime_header(filename))
                continue

            try:
                if content_type == "text/plain" and not body_text:
                    body_text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
                elif content_type == "text/html" and not body_html:
                    body_html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
            except Exception:
                continue
    else:
        try:
            body_text = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore")
        except Exception:
            body_text = str(msg.get_payload())

    return {
        "subject":     _decode_mime_header(msg.get("Subject", "")),
        "from":        _decode_mime_header(msg.get("From", "")),
        "to":          _decode_mime_header(msg.get("To", "")),
        "date":        msg.get("Date", ""),
        "message_id":  msg.get("Message-ID", ""),
        "body_text":   body_text,
        "body_html":   body_html,
        "attachments": attachments,
    }


def _connect_imap() -> imaplib.IMAP4_SSL:
    email_addr, password = _get_credentials()
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(email_addr, password)
    return imap


def _safe_logout(imap) -> None:
    try:
        imap.logout()
    except Exception:
        pass


def _fetch_uids(imap, uids: list) -> list:
    """Fetch and parse a list of UIDs, most recent first."""
    emails = []
    for uid in reversed(uids):
        typ, msg_data = imap.uid("fetch", uid, "(BODY.PEEK[])")
        if not msg_data or not msg_data[0]:
            continue
        parsed = _parse_email(msg_data[0][1])
        parsed["uid"] = uid
        emails.append(parsed)
    return emails


# ---------------------------------------------------------------------------
# 1. CONNECTION
# ---------------------------------------------------------------------------

def test_connection() -> str:
    """Verify both IMAP and SMTP login succeed. Run this first after setup."""
    try:
        email_addr, password = _get_credentials()
    except Exception as e:
        return _respond(str(e))

    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        imap.login(email_addr, password)
        _safe_logout(imap)
    except Exception as e:
        return _respond(f"IMAP connection failed: {e}")

    try:
        smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
        smtp.login(email_addr, password)
        smtp.quit()
    except Exception as e:
        return _respond(f"SMTP connection failed: {e}")

    return _respond(f"Connected successfully as {email_addr}. IMAP and SMTP both working.")


# ---------------------------------------------------------------------------
# 2. SEND / REPLY / FORWARD
# ---------------------------------------------------------------------------

def send_email(to: str, subject: str, body: str, cc: str = None, bcc: str = None,
                html: bool = False, attachments: list = None) -> str:
    try:
        email_addr, password = _get_credentials()
    except Exception as e:
        return _respond(str(e))

    try:
        msg = MIMEMultipart()
        msg["From"] = email_addr
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        msg.attach(MIMEText(body, "html" if html else "plain"))

        if attachments:
            for path in attachments:
                if not os.path.exists(path):
                    _respond(f"Attachment not found, skipping: {path}")
                    continue
                part = MIMEBase("application", "octet-stream")
                with open(path, "rb") as f:
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(path)}"')
                msg.attach(part)

        recipients = _split_addresses(to)
        if cc:
            recipients += _split_addresses(cc)
        if bcc:
            recipients += _split_addresses(bcc)

        smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
        smtp.login(email_addr, password)
        smtp.sendmail(email_addr, recipients, msg.as_string())
        smtp.quit()

        _log_sent(to, subject)
        return _respond(f"Email sent to {to}: '{subject}'")
    except Exception as e:
        return _respond(f"Failed to send email: {e}")


def reply_to_email(uid: str, body: str, folder: str = "INBOX") -> str:
    original = get_email_by_id(uid, folder, _quiet=True)
    if not original:
        return _respond(f"Could not find email {uid} to reply to.")

    try:
        email_addr, password = _get_credentials()
    except Exception as e:
        return _respond(str(e))

    try:
        subject = original["subject"]
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        addr_match = re.search(r"<(.+?)>", original["from"])
        reply_to_addr = addr_match.group(1) if addr_match else original["from"]

        msg = MIMEMultipart()
        msg["From"] = email_addr
        msg["To"] = reply_to_addr
        msg["Subject"] = subject
        if original["message_id"]:
            msg["In-Reply-To"] = original["message_id"]
            msg["References"] = original["message_id"]
        msg.attach(MIMEText(body, "plain"))

        smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
        smtp.login(email_addr, password)
        smtp.sendmail(email_addr, [reply_to_addr], msg.as_string())
        smtp.quit()

        _log_sent(reply_to_addr, subject)
        return _respond(f"Replied to {reply_to_addr}.")
    except Exception as e:
        return _respond(f"Failed to send reply: {e}")


def forward_email(uid: str, to: str, note: str = "", folder: str = "INBOX") -> str:
    original = get_email_by_id(uid, folder, _quiet=True)
    if not original:
        return _respond(f"Could not find email {uid} to forward.")

    try:
        email_addr, password = _get_credentials()
    except Exception as e:
        return _respond(str(e))

    try:
        subject = original["subject"]
        if not subject.lower().startswith("fwd:"):
            subject = f"Fwd: {subject}"

        forwarded_body = (
            f"{note}\n\n"
            f"---------- Forwarded message ----------\n"
            f"From: {original['from']}\n"
            f"Date: {original['date']}\n"
            f"Subject: {original['subject']}\n\n"
            f"{original['body_text']}"
        )

        msg = MIMEMultipart()
        msg["From"] = email_addr
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(forwarded_body, "plain"))

        smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
        smtp.login(email_addr, password)
        smtp.sendmail(email_addr, _split_addresses(to), msg.as_string())
        smtp.quit()

        _log_sent(to, subject)
        return _respond(f"Forwarded to {to}.")
    except Exception as e:
        return _respond(f"Failed to forward: {e}")


# ---------------------------------------------------------------------------
# 3. READ & SEARCH
# ---------------------------------------------------------------------------

def get_recent_emails(n: int = 10, folder: str = "INBOX") -> list:
    try:
        imap = _connect_imap()
    except Exception as e:
        _respond(str(e))
        return []
    try:
        imap.select(folder, readonly=True)
        typ, data = imap.uid("search", None, "ALL")
        uids = [u.decode() for u in data[0].split()][-n:]
        emails = _fetch_uids(imap, uids)
        print(f"  [GMAIL] Last {len(emails)} email(s) in {folder}:")
        for e in emails:
            print(f"    [{e['uid']}] {e['from']} — {e['subject']}  ({e['date']})")
        return emails
    except Exception as ex:
        _respond(f"Failed to fetch emails: {ex}")
        return []
    finally:
        _safe_logout(imap)


def get_unread_emails(n: int = 10) -> list:
    try:
        imap = _connect_imap()
    except Exception as e:
        _respond(str(e))
        return []
    try:
        imap.select("INBOX", readonly=True)
        typ, data = imap.uid("search", None, "UNSEEN")
        uids = [u.decode() for u in data[0].split()][-n:]
        emails = _fetch_uids(imap, uids)
        print(f"  [GMAIL] {len(emails)} unread email(s):")
        for e in emails:
            print(f"    [{e['uid']}] {e['from']} — {e['subject']}")
        return emails
    except Exception as ex:
        _respond(f"Failed to fetch unread emails: {ex}")
        return []
    finally:
        _safe_logout(imap)


def search_emails(query: str, n: int = 10) -> list:
    """Full Gmail search syntax works here — e.g. 'from:boss is:unread newer_than:2d'."""
    try:
        imap = _connect_imap()
    except Exception as e:
        _respond(str(e))
        return []
    try:
        imap.select("INBOX", readonly=True)
        escaped = query.replace('"', '\\"')
        typ, data = imap.uid("search", None, "X-GM-RAW", f'"{escaped}"')
        uids = [u.decode() for u in data[0].split()][-n:]
        emails = _fetch_uids(imap, uids)
        print(f"  [GMAIL] Found {len(emails)} email(s) matching '{query}':")
        for e in emails:
            print(f"    [{e['uid']}] {e['from']} — {e['subject']}")
        return emails
    except Exception as ex:
        _respond(f"Search failed: {ex}")
        return []
    finally:
        _safe_logout(imap)


def get_email_by_id(uid: str, folder: str = "INBOX", _quiet: bool = False) -> dict:
    """Full detail for one email, including body and attachment list."""
    try:
        imap = _connect_imap()
    except Exception as e:
        _respond(str(e))
        return {}
    try:
        imap.select(folder, readonly=True)
        typ, msg_data = imap.uid("fetch", uid, "(BODY.PEEK[])")
        if not msg_data or not msg_data[0]:
            _respond(f"Email {uid} not found.")
            return {}
        parsed = _parse_email(msg_data[0][1])
        parsed["uid"] = uid
        if not _quiet:
            print(f"  [GMAIL] From: {parsed['from']}")
            print(f"  [GMAIL] Subject: {parsed['subject']}")
            print(f"  [GMAIL] Date: {parsed['date']}")
            print(f"  [GMAIL] Body:\n{parsed['body_text'][:2000] or '(no plain text body)'}")
            if parsed["attachments"]:
                print(f"  [GMAIL] Attachments: {', '.join(parsed['attachments'])}")
        return parsed
    except Exception as ex:
        _respond(f"Failed to fetch email: {ex}")
        return {}
    finally:
        _safe_logout(imap)


# ---------------------------------------------------------------------------
# 4. FLAGS — READ / UNREAD / STAR
# ---------------------------------------------------------------------------

def _set_flag(uid: str, flag: str, add: bool, folder: str = "INBOX") -> str:
    try:
        imap = _connect_imap()
    except Exception as e:
        return _respond(str(e))
    try:
        imap.select(folder)
        imap.uid("store", uid, "+FLAGS" if add else "-FLAGS", flag)
        return _respond(f"Updated {flag} on email {uid}.")
    except Exception as ex:
        return _respond(f"Failed to update email: {ex}")
    finally:
        _safe_logout(imap)


def mark_as_read(uid: str) -> str:
    return _set_flag(uid, "\\Seen", add=True)


def mark_as_unread(uid: str) -> str:
    return _set_flag(uid, "\\Seen", add=False)


def star_email(uid: str) -> str:
    return _set_flag(uid, "\\Flagged", add=True)


def unstar_email(uid: str) -> str:
    return _set_flag(uid, "\\Flagged", add=False)


# ---------------------------------------------------------------------------
# 5. ORGANIZE — ARCHIVE / DELETE / LABELS
# ---------------------------------------------------------------------------

def archive_email(uid: str) -> str:
    try:
        imap = _connect_imap()
    except Exception as e:
        return _respond(str(e))
    try:
        imap.select("INBOX")
        imap.uid("store", uid, "-X-GM-LABELS", "(\\Inbox)")
        return _respond(f"Archived email {uid}.")
    except Exception as ex:
        return _respond(f"Failed to archive: {ex}")
    finally:
        _safe_logout(imap)


def delete_email(uid: str) -> str:
    try:
        imap = _connect_imap()
    except Exception as e:
        return _respond(str(e))
    try:
        imap.select("INBOX")
        imap.uid("store", uid, "+X-GM-LABELS", "(\\Trash)")
        return _respond(f"Moved email {uid} to Trash.")
    except Exception as ex:
        return _respond(f"Failed to delete: {ex}")
    finally:
        _safe_logout(imap)


def add_label(uid: str, label: str) -> str:
    try:
        imap = _connect_imap()
    except Exception as e:
        return _respond(str(e))
    try:
        imap.select("INBOX")
        imap.uid("store", uid, "+X-GM-LABELS", f'("{label}")')
        return _respond(f"Added label '{label}' to email {uid}.")
    except Exception as ex:
        return _respond(f"Failed to add label: {ex}")
    finally:
        _safe_logout(imap)


def remove_label(uid: str, label: str) -> str:
    try:
        imap = _connect_imap()
    except Exception as e:
        return _respond(str(e))
    try:
        imap.select("INBOX")
        imap.uid("store", uid, "-X-GM-LABELS", f'("{label}")')
        return _respond(f"Removed label '{label}' from email {uid}.")
    except Exception as ex:
        return _respond(f"Failed to remove label: {ex}")
    finally:
        _safe_logout(imap)


def list_labels() -> list:
    try:
        imap = _connect_imap()
    except Exception as e:
        _respond(str(e))
        return []
    try:
        typ, folders = imap.list()
        labels = []
        for f in folders:
            decoded = f.decode(errors="ignore")
            match = re.search(r'"([^"]+)"$', decoded)
            if match:
                labels.append(match.group(1))
        print(f"  [GMAIL] {len(labels)} label(s)/folder(s):")
        for l in labels:
            print(f"    - {l}")
        return labels
    except Exception as ex:
        _respond(f"Failed to list labels: {ex}")
        return []
    finally:
        _safe_logout(imap)


# ---------------------------------------------------------------------------
# 6. DRAFTS
# ---------------------------------------------------------------------------

def save_draft(to: str, subject: str, body: str) -> str:
    try:
        email_addr, _ = _get_credentials()
        imap = _connect_imap()
    except Exception as e:
        return _respond(str(e))
    try:
        msg = MIMEMultipart()
        msg["From"] = email_addr
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        imap.append(DRAFTS_FOLDER, "", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        return _respond(f"Draft saved: '{subject}'")
    except Exception as e:
        return _respond(f"Failed to save draft: {e}")
    finally:
        _safe_logout(imap)


# ---------------------------------------------------------------------------
# 7. ATTACHMENTS
# ---------------------------------------------------------------------------

def download_attachments(uid: str, save_dir: str = None, folder: str = "INBOX") -> list:
    save_dir = save_dir or ATTACHMENT_DIR
    os.makedirs(save_dir, exist_ok=True)

    try:
        imap = _connect_imap()
    except Exception as e:
        _respond(str(e))
        return []
    try:
        imap.select(folder, readonly=True)
        typ, msg_data = imap.uid("fetch", uid, "(BODY.PEEK[])")
        if not msg_data or not msg_data[0]:
            _respond(f"Email {uid} not found.")
            return []

        msg = message_from_bytes(msg_data[0][1])
        saved = []
        for part in msg.walk():
            if "attachment" in str(part.get("Content-Disposition", "")):
                filename = part.get_filename()
                if filename:
                    filename = _decode_mime_header(filename)
                    filepath = os.path.join(save_dir, filename)
                    with open(filepath, "wb") as f:
                        f.write(part.get_payload(decode=True))
                    saved.append(filepath)

        print(f"  [GMAIL] Downloaded {len(saved)} attachment(s):")
        for s in saved:
            print(f"    - {s}")
        return saved
    except Exception as ex:
        _respond(f"Failed to download attachments: {ex}")
        return []
    finally:
        _safe_logout(imap)


# ---------------------------------------------------------------------------
# 8. SUMMARY & SENT LOG
# ---------------------------------------------------------------------------

def get_inbox_summary() -> str:
    try:
        imap = _connect_imap()
    except Exception as e:
        return _respond(str(e))
    try:
        imap.select("INBOX", readonly=True)
        typ, all_data = imap.uid("search", None, "ALL")
        typ, unread_data = imap.uid("search", None, "UNSEEN")

        all_uids = all_data[0].split()
        unread_count = len(unread_data[0].split())

        print("\n  [GMAIL] ── Inbox Summary ──")
        print(f"    Total emails: {len(all_uids)}")
        print(f"    Unread:       {unread_count}")

        recent = [u.decode() for u in all_uids[-5:]]
        if recent:
            print("    Last 5 senders:")
            for uid in reversed(recent):
                typ, msg_data = imap.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
                if msg_data and msg_data[0]:
                    header_msg = message_from_bytes(msg_data[0][1])
                    print(f"      {_decode_mime_header(header_msg.get('From', ''))} — {_decode_mime_header(header_msg.get('Subject', ''))}")

        return _respond("Inbox summary complete.")
    except Exception as ex:
        return _respond(f"Failed to get inbox summary: {ex}")
    finally:
        _safe_logout(imap)


def get_sent_log(n: int = 10) -> list:
    log = _load_json(SENT_LOG, [])[:n]
    print(f"  [GMAIL] Last {len(log)} sent email(s):")
    for item in log:
        print(f"    [{item['sent_at']}] To: {item['to']} — {item['subject']}")
    return log


# ---------------------------------------------------------------------------
# 9. COMMAND DISPATCHER — Natural Language Interface
# ---------------------------------------------------------------------------

def handle_email_command(user_input: str) -> str:
    """Main entry point — called from main.py for email-related commands."""
    text = user_input.lower().strip()

    if any(p in text for p in ["check my email", "check email", "check inbox", "inbox summary"]):
        return get_inbox_summary()

    if any(p in text for p in ["unread emails", "unread email", "show unread"]):
        get_unread_emails()
        return "Here are your unread emails."

    if any(p in text for p in ["recent emails", "recent email", "show inbox"]):
        get_recent_emails()
        return "Here are your recent emails."

    if any(p in text for p in ["sent emails", "emails i sent", "show sent"]):
        get_sent_log()
        return "Here are your recently sent emails."

    if any(p in text for p in ["test email connection", "test gmail", "check gmail connection"]):
        return test_connection()

    if any(p in text for p in ["show labels", "list labels", "email folders"]):
        list_labels()
        return "Here are your Gmail labels."

    match = re.search(r"search email(?:s)? for\s+(.+)", text)
    if match:
        search_emails(match.group(1).strip())
        return "Search complete."

    return _respond(f"No email command matched: '{user_input}'")


# ---------------------------------------------------------------------------
# Quick Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "="*55)
    print("   Cortex AI — Gmail Module Test")
    print("="*55 + "\n")

    print("--- Credential Check ---")
    try:
        _get_credentials()
        print("  Credentials found.")
    except Exception as e:
        print(f"  Expected (no .env configured yet): {e}")

    print("\n--- MIME Header Decoding ---")
    print(f"  Plain:   {_decode_mime_header('Hello World')}")
    print(f"  Encoded: {_decode_mime_header('=?UTF-8?B?SGVsbG8gV29ybGQ=?=')}")
    assert _decode_mime_header("=?UTF-8?B?SGVsbG8gV29ybGQ=?=") == "Hello World"
    print("  Header decoding correct.")

    print("\n--- Email Parsing (round-trip, no network needed) ---")
    test_msg = MIMEMultipart()
    test_msg["From"] = "Alice <alice@example.com>"
    test_msg["To"] = "bob@example.com"
    test_msg["Subject"] = "Test Subject"
    test_msg["Message-ID"] = "<test123@example.com>"
    test_msg["Date"] = "Mon, 1 Jan 2026 10:00:00 +0000"
    test_msg.attach(MIMEText("This is the plain text body.", "plain"))

    part = MIMEBase("application", "octet-stream")
    part.set_payload(b"fake file content for testing")
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", 'attachment; filename="report.txt"')
    test_msg.attach(part)

    parsed = _parse_email(test_msg.as_bytes())
    print(f"  Subject:     {parsed['subject']}")
    print(f"  From:        {parsed['from']}")
    print(f"  Body:        {parsed['body_text'].strip()}")
    print(f"  Attachments: {parsed['attachments']}")

    assert parsed["subject"] == "Test Subject"
    assert "alice@example.com" in parsed["from"]
    assert "plain text body" in parsed["body_text"]
    assert "report.txt" in parsed["attachments"]
    print("   All parsing assertions passed.")

    print("\n--- Sent Log ---")
    _log_sent("test@example.com", "Test Email 1")
    _log_sent("another@example.com", "Test Email 2")
    get_sent_log()

    print("\n--- Live Connection Attempt ---")
    result = test_connection()
    print(f"  Result: {result}")

    print("\n--- Dispatcher Tests ---\n")
    for cmd in ["show sent emails", "unknown gibberish command"]:
        print(f"  > {cmd}")
        handle_email_command(cmd)
        print()

    print("\n Gmail Module Test Complete!")