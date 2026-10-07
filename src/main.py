# holy imports
# python imports
import os
import dotenv
import base64
import logging
from pathlib import Path
from email.message import EmailMessage
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
# Package imports
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import gspread
# file imports
from email_template import email_creator, mixer_email_creator
from status import Status
import validators

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)

dotenv.load_dotenv()

SERVICE_ACCOUNT_PATH = "credentials.json"

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]

PROD_ENV = os.getenv("PROD_ENV") == "TRUE"
DAILY_CAP = int(os.getenv("TOTAL_AMOUNT_PER_DAY", "40"))
CENTRAL_TZ = ZoneInfo("America/Chicago")
SEND_WINDOW_START_HOUR = 6
SEND_WINDOW_END_HOUR = 17

if PROD_ENV:
    SHEET_NAME = "Spring 2026 Email Spammer"
else:
    SHEET_NAME = "Spring 2026 Email Spammer Test"


# Statuses that mean "still needs sending" ("SCHEDULED" is a leftover from the old flow).
START_STATUSES = {"", Status.NEW.value, "DRAFTED", "SCHEDULED"}


def is_within_send_window(now_utc):
    central_time = now_utc.astimezone(CENTRAL_TZ)
    if central_time.weekday() >= 5:
        return False
    return SEND_WINDOW_START_HOUR <= central_time.hour <= SEND_WINDOW_END_HOUR


def build_message(to, subject, body):
    msg = EmailMessage()

    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body, subtype="html")

    encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": encoded}


def send_message(service, to, subject, body):
    try:
        message = build_message(to, subject, body)
        sent_message = service.users().messages().send(
            userId="me", body=message
        ).execute()
        print(f"Message sent! Message ID: {sent_message['id']}")
        return sent_message
    except Exception as e:
        print(f"Error sending message: {e}")
        return None


def get_gmail_service():
    creds = None
    token_path = "token.json"
    oauth_client_path = "oauth_client.json"

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                oauth_client_path, GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_gmail_signature(gmail_service, send_as_email=None):
    send_as_list = gmail_service.users().settings().sendAs().list(userId="me").execute()
    aliases = send_as_list.get("sendAs", [])

    if send_as_email:
        alias = next(
            (item for item in aliases if item.get("sendAsEmail") == send_as_email),
            None,
        )
    else:
        alias = next((item for item in aliases if item.get("isPrimary")), None)

    if not alias and aliases:
        alias = aliases[0]

    return (alias or {}).get("signature", "")


def get_spreadsheet():
    client = gspread.service_account(filename=SERVICE_ACCOUNT_PATH)
    return client.open(SHEET_NAME)


def collect_rows(spreadsheet):
    rows = spreadsheet.sheet1.get_all_records()
    scheduler = spreadsheet.get_worksheet(1).get_all_records()
    return rows, scheduler


def row_number(row):
    return int(row["ID"]) + 1


def batch_update_cells(worksheet, updates):
    payload = [{"range": cell, "values": [[value]]} for cell, value in updates.items()]
    worksheet.batch_update(payload)


def sends_today(last_sent_utc, actions_per_day):
    """The Scheduler tab keeps a running count; it resets on the first run of a new day."""
    if last_sent_utc.astimezone(CENTRAL_TZ).date() < datetime.now(CENTRAL_TZ).date():
        return 0
    return actions_per_day


def create_email(row, officer_name, officer_role, signature_html):
    creator = mixer_email_creator if row["Mixer"] == "TRUE" else email_creator
    return creator(
        contact_first_name=row["FirstName"],
        contact_last_name=row["LastName"],
        company=row["Company"],
        officer_name=officer_name,
        officer_role=officer_role,
        signature_html=signature_html,
    )


def mark_failed(contacts_ws, row, error):
    batch_update_cells(
        contacts_ws,
        {
            f"F{row_number(row)}": Status.FAILED.value,
            f"I{row_number(row)}": str(error),
        },
    )


def main():
    if not is_within_send_window(datetime.now(timezone.utc)):
        logging.info("Outside the send window; nothing to do.")
        return

    try:
        sheet = get_spreadsheet()
        rows, scheduler = collect_rows(sheet)
        (
            last_sent_utc,
            actions_per_day,
            officer_name,
            officer_role,
            stop_action,
        ) = validators.validate_scheduler(scheduler)
    except Exception as e:
        logging.exception(e)
        return

    if stop_action:
        logging.info("StopAction is enabled; stopping execution.")
        return

    actions_per_day = sends_today(last_sent_utc, actions_per_day)
    if actions_per_day >= DAILY_CAP:
        logging.info("Daily cap of %s reached.", DAILY_CAP)
        return

    contacts_ws = sheet.worksheet("Sheet1")

    try:
        gmail_service = get_gmail_service()
    except Exception as e:
        logging.exception(e)
        return

    try:
        signature_html = get_gmail_signature(gmail_service)
    except Exception as e:
        logging.exception(e)
        signature_html = ""

    scheduler_ws = sheet.worksheet("Scheduler")
    # Rows at or below this ID were already handled; skip them without re-validating.
    last_sent_row_id = int(scheduler_ws.acell("E2").value or 0)

    # Send exactly one email per run: the first row that is still NEW.
    for row in rows:
        if validators.is_empty_row(row):
            break

        try:
            row_id = int(row["ID"])
        except (KeyError, TypeError, ValueError):
            continue
        if row_id <= last_sent_row_id:
            continue
        if str(row.get("Status") or "") not in START_STATUSES:
            continue

        try:
            row = validators.validate_row(row)
            subject, body = create_email(row, officer_name, officer_role, signature_html)
        except Exception as e:
            # Bad data in this row; flag it and move on to the next candidate.
            logging.exception(e)
            mark_failed(contacts_ws, row, e)
            continue

        if not send_message(gmail_service, row["Email"], subject, body):
            return  # Gmail error: leave the row NEW and retry on the next run.

        now_utc = datetime.now(timezone.utc)
        batch_update_cells(contacts_ws, {f"F{row_number(row)}": Status.SENT.value})
        batch_update_cells(
            scheduler_ws,
            {"A2": now_utc.isoformat(), "B2": actions_per_day + 1, "E2": row_id},
        )
        return

    logging.info("No NEW contacts left to send to.")


if __name__ == "__main__":
    main()
