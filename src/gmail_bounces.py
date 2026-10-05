"""Detect hard bounces by reading Mailer-Daemon failure notices from the sending Gmail mailbox."""
import base64
import re

EMAIL_PATTERN = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")
BOUNCE_QUERY = "from:(mailer-daemon OR postmaster) newer_than:{days}d"


def _decode(data):
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def _collect_text(part, chunks):
    data = part.get("body", {}).get("data")
    if data:
        chunks.append(_decode(data))
    for sub in part.get("parts", []):
        _collect_text(sub, chunks)


def _header(message, name):
    for h in message["payload"].get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _is_delay_notice(message):
    subject = _header(message, "Subject").lower()
    return "delay" in subject or "delayed" in subject


def _failed_addresses(message, known_addresses):
    """Prefer the X-Failed-Recipients header; otherwise any known contact address in the body."""
    header = _header(message, "X-Failed-Recipients")
    if header:
        return {a.lower() for a in EMAIL_PATTERN.findall(header)}

    chunks = []
    _collect_text(message["payload"], chunks)
    found = {a.lower() for a in EMAIL_PATTERN.findall("\n".join(chunks))}
    return found & known_addresses


def fetch_bounces(gmail_service, known_addresses, lookback_days=14):
    """Return the set of lowercase addresses that hard-bounced.

    `known_addresses` is the set of lowercase contact addresses, used to pick the failed
    recipient out of bounce bodies that lack an X-Failed-Recipients header.
    """
    bounced = set()
    page_token = None
    while True:
        listing = (
            gmail_service.users()
            .messages()
            .list(
                userId="me",
                q=BOUNCE_QUERY.format(days=lookback_days),
                pageToken=page_token,
            )
            .execute()
        )
        for ref in listing.get("messages", []):
            message = (
                gmail_service.users()
                .messages()
                .get(userId="me", id=ref["id"], format="full")
                .execute()
            )
            if _is_delay_notice(message):
                continue
            bounced |= _failed_addresses(message, known_addresses)

        page_token = listing.get("nextPageToken")
        if not page_token:
            break

    return bounced
