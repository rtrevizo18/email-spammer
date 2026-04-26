# holy imports
import os
import dotenv
import base64
import gspread
import logging
import time
from datetime import datetime, timezone, timedelta
from enum import Enum
from email_validator import validate_email
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from email_template import email_creator

dotenv.load_dotenv()

SHEET_NAME = "Spring 2026 Email Spammer Test"
SERVICE_ACCOUNT_PATH = "credentials.json"

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]

TOTAL_AMOUNT_PER_DAY = int(os.getenv("TOTAL_AMOUNT_PER_DAY", "20"))
MAX_DRAFTS_PER_RUN = int(os.getenv("MAX_DRAFTS_PER_RUN", "3"))
MAX_SENDS_PER_RUN = int(os.getenv("MAX_SENDS_PER_RUN", "1"))
MIN_MINUTES_BETWEEN_SENDS = int(os.getenv("MIN_MINUTES_BETWEEN_SENDS", "20"))
SCHEDULE_LEAD_MINUTES = int(os.getenv("SCHEDULE_LEAD_MINUTES", "5"))

class Status(Enum):
    NEW = "NEW"
    DRAFTED = "DRAFTED"
    SCHEDULED = "SCHEDULED"
    SENT = "SENT"
    FAILED = "FAILED"


def validate_scheduler(scheduler):
    columns = ["LastSentAtUTC", "ActionsPerDay", "Officer", "Role"]

    if len(scheduler) != 1:
        raise Exception(f"Expected number of rows: 1, Given: {len(scheduler)}")

    scheduler_row = scheduler[0]

    for col in columns:
        if col not in scheduler_row:
            raise Exception(f"Column {col} does not exist on scheduler row.")

    last_sent_utc = scheduler_row["LastSentAtUTC"]
    if not last_sent_utc:
        last_sent_utc = datetime.now(timezone.utc).isoformat()

    dt = datetime.fromisoformat(last_sent_utc)
    if dt.tzinfo != timezone.utc:
        raise Exception("Read timestamp does not correspond to UTC timezone.")

    amount_sent = scheduler_row["ActionsPerDay"]
    if not isinstance(amount_sent, int):
        raise Exception("ActionsPerDay is not a number.")

    officer_name = scheduler_row["Officer"]
    if not isinstance(officer_name, str) or len(officer_name) == 0:
        raise Exception("Officer name is not a non-empty string.")

    officer_role = scheduler_row["Role"]
    if not isinstance(officer_role, str) or len(officer_role) == 0:
        raise Exception("Officer role is not a non-empty string.")

    return dt, amount_sent, officer_name, officer_role


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


# This will throw a custom error, just let it.
def check_email(email):
    email_info = validate_email(email, check_deliverability=True)
    return email_info.normalized


def validate_contact(row):
    columns = ["Company", "FirstName", "LastName", "Email"]

    for col in columns:
        if col not in row:
            raise Exception(f"Column {col} does not exist on this row.")

        value = row[col]
        if not isinstance(value, str):
            raise Exception(f"Value of column {col} must be string, got {type(value)}.")
        if len(value) == 0:
            raise Exception(f"Value of column {col} is empty.")

    row["Email"] = check_email(row["Email"])
    return row


def validate_row(row):
    validated_contact_row = validate_contact(row)

    status = validated_contact_row.get("Status")
    if not status:
        status = Status.NEW.value

    try:
        validated_contact_row["Status"] = Status(status)
    except ValueError:
        raise Exception(f"Invalid status in sheet: {status}")

    return validated_contact_row


def parse_boolish(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    if isinstance(value, (int, float)):
        return value != 0
    return False


def is_blank(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def is_empty_terminator_row(row):
    if is_blank(row.get("ID")):
        return False

    content_columns = [
        "Company",
        "FirstName",
        "LastName",
        "Email",
        "Status",
        "Last Contacted",
        "DraftID",
        "ScheduledAtUTC",
        "Notes",
    ]

    return all(is_blank(row.get(column)) for column in content_columns)


def row_number(row):
    return int(row["ID"]) + 1


def parse_row_id(value):
    if value is None:
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return 0
        try:
            return max(0, int(float(text)))
        except ValueError:
            return 0
    return 0


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
    return parse_row_id(scheduler_ws.acell("E2").value)


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
    if not parse_boolish(row.get("ApproveSend")):
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
        last_sent_utc, actions_per_day, officer_name, officer_role = validate_scheduler(
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
        row for row in rows if parse_row_id(row.get("ID")) > last_sent_row_id
    ]

    for row in rows_to_process:
        try:
            if is_empty_terminator_row(row):
                logging.info(
                    "Encountered empty terminator row at ID=%s. Stopping processing.",
                    row.get("ID"),
                )
                break

            row = validate_row(row)
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
                    sent_row_id = parse_row_id(row.get("ID"))
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
