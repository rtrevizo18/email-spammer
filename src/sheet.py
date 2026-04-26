# holy imports
# python imports
import os
import dotenv
import base64
import logging
import time
from datetime import datetime, timezone, timedelta
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

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]

TOTAL_AMOUNT_PER_DAY = int(os.getenv("TOTAL_AMOUNT_PER_DAY", "20"))
MAX_DRAFTS_PER_RUN = int(os.getenv("MAX_DRAFTS_PER_RUN", "3"))
MAX_SENDS_PER_RUN = int(os.getenv("MAX_SENDS_PER_RUN", "1"))
MIN_MINUTES_BETWEEN_SENDS = int(os.getenv("MIN_MINUTES_BETWEEN_SENDS", "20"))
SCHEDULE_LEAD_MINUTES = int(os.getenv("SCHEDULE_LEAD_MINUTES", "5"))


def create_draft(service, to, subject, body):
    message = f"To: {to}\r\nSubject: {subject}\r\n\r\n{body}"
    encoded = base64.urlsafe_b64encode(message.encode()).decode()
    draft = {"message": {"raw": encoded}}
    return service.users().drafts().create(userId="me", body=draft).execute()


def send_draft(service, draft_id):
    try:
        sent_message = service.users().drafts().send(
            userId="me", body={"id": draft_id}
        ).execute()
        print(f"Draft sent! Message ID: {sent_message['id']}")
        return sent_message
    except Exception as e:
        print(f"Error sending draft: {e}")
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
    return max(minimum_next_from_last_send, minimum_next_from_now)


def process_new_row(gmail_service, contacts_ws, row, officer_name, officer_role):
    subject, body = email_creator(
        contact_first_name=row["FirstName"],
        company=row["Company"],
        officer_name=officer_name,
        officer_role=officer_role,
    )

    draft = create_draft(gmail_service, row["Email"], subject, body)

    current_row_number = row_number(row)
    batch_update_cells(
        contacts_ws,
        {
            f"I{current_row_number}": draft["id"],
            f"F{current_row_number}": Status.DRAFTED.value,
        },
    )


def process_drafted_row(sheet, row, last_sent_utc):
    if row.get("ApproveSend") != "TRUE":
        return False

    draft_id = row.get("DraftID")
    if not draft_id:
        return False

    scheduled_time = compute_schedule_time(last_sent_utc)

    contacts_ws = sheet.worksheet("Sheet1")
    current_row_number = row_number(row)
    batch_update_cells(
        contacts_ws,
        {
            f"J{current_row_number}": scheduled_time.isoformat(),
            f"F{current_row_number}": Status.SCHEDULED.value,
        },
    )
    return True


def process_scheduled_row(gmail_service, contacts_ws, row):
    scheduled_at_text = row.get("ScheduledAtUTC")
    if not scheduled_at_text:
        return False

    draft_id = row.get("DraftID")
    if not draft_id:
        return False

    scheduled_at = datetime.fromisoformat(scheduled_at_text)
    if datetime.now(timezone.utc) < scheduled_at:
        return False

    sent = send_draft(gmail_service, draft_id)
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
    now_utc = datetime.now(timezone.utc)
    if last_sent_utc.date() < now_utc.date():
        return actions_per_day * 0
    return actions_per_day


def main():
    try:
        sheet = get_spreadsheet()
        rows, scheduler = collect_rows(sheet)
        last_sent_utc, actions_per_day, officer_name, officer_role = validators.validate_scheduler(
            scheduler
        )
    except Exception as e:
        logging.exception(e)
        return

    actions_per_day = reset_daily_counter_if_new_day(last_sent_utc, actions_per_day)

    try:
        gmail_service = get_gmail_service()
    except Exception as e:
        logging.exception(e)
        return

    contacts_ws = sheet.worksheet("Sheet1")
    last_sent_row_id = get_last_sent_row_id(sheet)

    drafts_created = 0
    sends_made = 0
    state_changed = False

    rows_to_process = [
        row for row in rows if int(row["ID"]) > last_sent_row_id # type: ignore
    ]

    for row in rows_to_process:
        try:
            if validators.is_empty_row(row):
                logging.info(
                    f"Encountered empty terminator row at ID={row.get("ID")}s. Stopping processing."
                )
                break

            row = validators.validate_row(row)
            status = row["Status"]

            if status == Status.NEW and drafts_created < MAX_DRAFTS_PER_RUN:
                process_new_row(
                    gmail_service,
                    contacts_ws,
                    row,
                    officer_name,
                    officer_role,
                )
                drafts_created += 1
                state_changed = True
                continue

            if status == Status.DRAFTED:
                did_schedule = process_drafted_row(sheet, row, last_sent_utc)
                if did_schedule:
                    last_sent_utc = compute_schedule_time(last_sent_utc)
                    state_changed = True
                continue

            if (
                status == Status.SCHEDULED
                and sends_made < MAX_SENDS_PER_RUN
                and actions_per_day < TOTAL_AMOUNT_PER_DAY
            ):
                was_sent = process_scheduled_row(gmail_service, contacts_ws, row)
                if was_sent:
                    sends_made += 1
                    actions_per_day += 1
                    last_sent_utc = datetime.now(timezone.utc)
                    sent_row_id = int(row.get("ID"))
                    if sent_row_id > last_sent_row_id:
                        last_sent_row_id = sent_row_id
                    state_changed = True

            time.sleep(1)

        except Exception as e:
            logging.exception(e)
            batch_update_cells(contacts_ws, {
                f"K{row["ID"]}": str(e)
            })
            return

    if state_changed:
        update_scheduler_row(
            sheet,
            last_sent_utc,
            actions_per_day,
            last_sent_row_id,
        )


if __name__ == "__main__":
    main()
