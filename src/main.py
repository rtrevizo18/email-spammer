# holy imports
# python imports
import os
import dotenv
import base64
import logging
import time
from email.message import EmailMessage
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
# Package imports
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import gspread
# file imports
from email_template import email_creator
from status import Status
import validators

dotenv.load_dotenv()

SHEET_NAME = "Spring 2026 Email Spammer Test"
SERVICE_ACCOUNT_PATH = "credentials.json"

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]

TOTAL_AMOUNT_PER_DAY = int(os.getenv("TOTAL_AMOUNT_PER_DAY", "20"))
MAX_SCHEDULES_PER_RUN = int(os.getenv("MAX_SCHEDULES_PER_RUN", "3"))
MAX_SENDS_PER_RUN = int(os.getenv("MAX_SENDS_PER_RUN", "1"))
MIN_MINUTES_BETWEEN_SENDS = int(os.getenv("MIN_MINUTES_BETWEEN_SENDS", "20"))
SCHEDULE_LEAD_MINUTES = int(os.getenv("SCHEDULE_LEAD_MINUTES", "5"))
CENTRAL_TZ = ZoneInfo("America/Chicago")
SEND_WINDOW_START_HOUR = 6
SEND_WINDOW_END_HOUR = 17




def is_within_send_window(now_utc):
    central_time = now_utc.astimezone(CENTRAL_TZ)
    if central_time.weekday() >= 5:
        return False
    return SEND_WINDOW_START_HOUR <= central_time.hour <= SEND_WINDOW_END_HOUR


def next_send_time(after_utc):
    candidate = after_utc.astimezone(CENTRAL_TZ)
    # Normalize to the next allowed CST weekday window.
    while True:
        if candidate.weekday() >= 5:
            days_ahead = 7 - candidate.weekday()
            candidate = candidate + timedelta(days=days_ahead)
            candidate = candidate.replace(
                hour=SEND_WINDOW_START_HOUR, minute=0, second=0, microsecond=0
            )
            continue
        if candidate.hour < SEND_WINDOW_START_HOUR:
            candidate = candidate.replace(
                hour=SEND_WINDOW_START_HOUR, minute=0, second=0, microsecond=0
            )
            break
        if candidate.hour > SEND_WINDOW_END_HOUR:
            candidate = candidate + timedelta(days=1)
            candidate = candidate.replace(
                hour=SEND_WINDOW_START_HOUR, minute=0, second=0, microsecond=0
            )
            continue
        break

    return candidate.astimezone(timezone.utc)


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
    contact_sheet = spreadsheet.sheet1
    rows = contact_sheet.get_all_records()

    scheduler_sheet = spreadsheet.get_worksheet(1)
    scheduler = scheduler_sheet.get_all_records()

    return rows, scheduler

def row_number(row):
    return int(row["ID"]) + 1

def batch_update_cells(worksheet, updates):
    payload = [{"range": cell, "values": [[value]]} for cell, value in updates.items()]
    worksheet.batch_update(payload)


def update_scheduler_row(sheet, last_sent_utc, actions_per_day, last_sent_row_id):
    scheduler_ws = sheet.worksheet("Scheduler")
    batch_update_cells(
        scheduler_ws,
        {
            "A2": last_sent_utc.isoformat(),
            "B2": actions_per_day,
            "E2": last_sent_row_id,
        },
    )


def get_last_sent_row_id(sheet):
    scheduler_ws = sheet.worksheet("Scheduler")
    return int(scheduler_ws.acell("E2").value)


def compute_schedule_time(last_sent_utc):
    now_utc = datetime.now(timezone.utc)
    minimum_next_from_last_send = last_sent_utc + timedelta(
        minutes=MIN_MINUTES_BETWEEN_SENDS
    )
    minimum_next_from_now = now_utc + timedelta(minutes=SCHEDULE_LEAD_MINUTES)
    return next_send_time(max(minimum_next_from_last_send, minimum_next_from_now))


def process_new_row(contacts_ws, row, last_sent_utc):
    scheduled_time = compute_schedule_time(last_sent_utc)

    current_row_number = row_number(row)
    batch_update_cells(
        contacts_ws,
        {
            f"H{current_row_number}": scheduled_time.isoformat(),
            f"F{current_row_number}": Status.SCHEDULED.value,
        },
    )
    return scheduled_time


def process_scheduled_row(
    gmail_service,
    contacts_ws,
    row,
    officer_name,
    officer_role,
    signature_html,
):
    scheduled_at_text = row.get("ScheduledAtUTC")
    if not scheduled_at_text:
        return False

    scheduled_at = datetime.fromisoformat(scheduled_at_text)
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)

    now_utc = datetime.now(timezone.utc)
    if now_utc < scheduled_at:
        return False

    if not is_within_send_window(now_utc):
        return False

    subject, body = email_creator(
        contact_first_name=row["FirstName"],
        company=row["Company"],
        officer_name=officer_name,
        officer_role=officer_role,
        signature_html=signature_html,
    )

    sent = send_message(gmail_service, row["Email"], subject, body)
    if not sent:
        return False

    current_row_number = row_number(row)
    batch_update_cells(
        contacts_ws,
        {
            f"F{current_row_number}": Status.SENT.value,
        },
    )
    return True


def reset_daily_counter_if_new_day(last_sent_utc, actions_per_day):
    now_central = datetime.now(CENTRAL_TZ)
    last_sent_central = last_sent_utc.astimezone(CENTRAL_TZ)
    if last_sent_central.date() < now_central.date():
        return actions_per_day * 0
    return actions_per_day


def main():
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

    actions_per_day = reset_daily_counter_if_new_day(last_sent_utc, actions_per_day)

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

    contacts_ws = sheet.worksheet("Sheet1")
    last_sent_row_id = get_last_sent_row_id(sheet)

    schedules_made = 0
    sends_made = 0
    state_changed = False

    rows_to_process = [
        row for row in rows
    ]

    filtered_rows = []
    for row_index, row in enumerate(rows_to_process, start=2):
        if validators.is_empty_row(row):
            filtered_rows.append(row)
            break

        row_id = row.get("ID")
        try:
            row_id_int = int(row_id) # type: ignore
        except (TypeError, ValueError):
            logging.warning(
                "Skipping row with invalid ID at sheet row %s: %r",
                row_index,
                row_id,
            )
            batch_update_cells(
                contacts_ws,
                {
                    f"I{row_index}": "Invalid ID; row skipped.",
                },
            )
            continue

        if row_id_int > last_sent_row_id:
            filtered_rows.append(row)

    for row in filtered_rows:
        try:
            if validators.is_empty_row(row):
                logging.info(
                    f"Encountered empty terminator row at ID={row.get('ID')}s. Stopping processing."
                )
                break

            row = validators.validate_row(row)
            status = row["Status"]

            if status == Status.NEW and schedules_made < MAX_SCHEDULES_PER_RUN:
                scheduled_time = process_new_row(contacts_ws, row, last_sent_utc)
                last_sent_utc = scheduled_time
                schedules_made += 1
                state_changed = True
                continue

            if (
                status == Status.SCHEDULED
                and sends_made < MAX_SENDS_PER_RUN
                and actions_per_day < TOTAL_AMOUNT_PER_DAY
            ):
                was_sent = process_scheduled_row(
                    gmail_service,
                    contacts_ws,
                    row,
                    officer_name,
                    officer_role,
                    signature_html,
                )
                if was_sent:
                    sends_made += 1
                    actions_per_day += 1
                    last_sent_utc = datetime.now(timezone.utc)
                    sent_row_id = int(row.get("ID"))
                    if sent_row_id > last_sent_row_id:
                        last_sent_row_id = sent_row_id
                    state_changed = True
            
            if state_changed:
                update_scheduler_row(
                    sheet,
                    last_sent_utc,
                    actions_per_day,
                    last_sent_row_id,
                )

            time.sleep(1)

        except Exception as e:
            logging.exception(e)
            row_id = row_number(row)
            batch_update_cells(contacts_ws, {
                f"I{row_id}": str(e)
            })
            return




if __name__ == "__main__":
    main()
