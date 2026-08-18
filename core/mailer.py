"""
Outreach email — entirely optional, and never automatic.

`send()` exists so you can dispatch a pitch you have already read and approved
without leaving the dashboard. Nothing in the codebase calls it on a schedule,
in a loop, or as part of generating anything: the only caller is the approval
button on the Backlinks page, one pitch per click. Leave SMTP blank and Lane B
works exactly the same — you copy the pitch and send it from your own mailbox.

Fails soft: a bad host, a refused login or a rejected address comes back as
{'ok': False, 'detail': "..."} in plain language.
"""

import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from . import config

TIMEOUT = 30

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


def valid_address(address: str) -> bool:
    return bool(EMAIL_RE.match((address or "").strip()))


def missing() -> list:
    """Which email settings are still empty. [] means sending is possible."""
    pairs = [
        ("the 'send pitches from' address", config.is_set("OUTREACH_FROM_EMAIL")),
        ("SMTP host", config.is_set("SMTP_HOST")),
        ("SMTP username", config.is_set("SMTP_USER")),
        ("SMTP password", config.is_set("SMTP_PASSWORD")),
    ]
    return [label for label, ok in pairs if not ok]


def configured() -> bool:
    """True when a pitch could be sent from here — not that one ever is."""
    return not missing()


def from_address() -> str:
    return config.get("OUTREACH_FROM_EMAIL")


def from_name() -> str:
    return config.get("OUTREACH_FROM_NAME")


def _port() -> int:
    try:
        return int(config.get("SMTP_PORT", "587"))
    except ValueError:
        return 587


def _build(to: str, subject: str, body: str, reply_to: str = "") -> EmailMessage:
    message = EmailMessage()
    sender = from_address()
    message["From"] = formataddr((from_name(), sender)) if from_name() else sender
    message["To"] = to
    message["Subject"] = subject
    message["Reply-To"] = reply_to or sender
    message.set_content(body)          # plain text: it's a personal email, not a mailshot
    return message


def send(to: str, subject: str, body: str, reply_to: str = "") -> dict:
    """
    Send ONE pitch. Called only from the approval button — see the module note.
    Returns {'ok': bool, 'detail': str}; never raises.
    """
    gaps = missing()
    if gaps:
        return {"ok": False,
                "detail": f"Email isn't set up — missing: {', '.join(gaps)}. Copy the "
                          "pitch instead, or fill these in under Settings → Outreach email."}
    to = (to or "").strip()
    if not valid_address(parseaddr(to)[1] or to):
        return {"ok": False, "detail": f"'{to}' doesn't look like an email address."}
    if not subject.strip() or not body.strip():
        return {"ok": False, "detail": "The pitch needs both a subject and a body."}

    host, port = config.get("SMTP_HOST"), _port()
    user, password = config.get("SMTP_USER"), config.get("SMTP_PASSWORD")
    message = _build(to, subject.strip(), body, reply_to)

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=TIMEOUT)
        with server:
            if port != 465:
                server.starttls(context=ssl.create_default_context())
            server.login(user, password)
            server.send_message(message)
        return {"ok": True, "detail": f"Pitch sent to {to} from {from_address()}."}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False,
                "detail": "The mail server refused the login. Most providers need an "
                          "app password here, not your normal mailbox password."}
    except smtplib.SMTPRecipientsRefused:
        return {"ok": False, "detail": f"The mail server refused the address {to}."}
    except smtplib.SMTPException as e:
        return {"ok": False, "detail": f"The mail server rejected the message: {e}"}
    except Exception as e:
        return {"ok": False, "detail": f"Couldn't reach {host}:{port} — {e}"}


def check() -> dict:
    """
    Connect and log in, but send nothing — the safe way to find out whether the
    approval button will work before you rely on it.
    """
    gaps = missing()
    if gaps:
        return {"ok": False, "detail": f"Not set up yet — missing: {', '.join(gaps)}."}
    host, port = config.get("SMTP_HOST"), _port()
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=TIMEOUT)
        with server:
            if port != 465:
                server.starttls(context=ssl.create_default_context())
            server.login(config.get("SMTP_USER"), config.get("SMTP_PASSWORD"))
        return {"ok": True,
                "detail": f"Logged in to {host}:{port}. Pitches would send from "
                          f"{from_address()}. Nothing was sent by this test."}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False,
                "detail": "Connected, but the login was refused — use an app password."}
    except Exception as e:
        return {"ok": False, "detail": f"Couldn't reach {host}:{port} — {e}"}
