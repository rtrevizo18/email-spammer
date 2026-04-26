import os
import dotenv
import base64
import gspread
import logging
from datetime import datetime, timezone
from enum import Enum
from email_validator import validate_email
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from email_template import email_creator

dotenv.load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SHEET_NAME = "Spring 2026 Email Spammer Test"
SERVICE_ACCOUNT_PATH = "credentials.json"

GOOGLE_SCOPES = [
  "https://www.googleapis.com/auth/spreadsheets",
  "https://www.googleapis.com/auth/drive"
]

GMAIL_SCOPES = [
  "https://www.googleapis.com/auth/gmail.compose"
]


def create_draft(service, to, subject, body):
  message = f"To: {to}\r\nSubject: {subject}\r\n\r{body}"

  encoded = base64.urlsafe_b64encode(message.encode()).decode()

  draft = {
    'message': {
      'raw': encoded
    }
  }

  return service.users().drafts().create(userId="me", body=draft).execute()


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
      flow = InstalledAppFlow.from_client_secrets_file(oauth_client_path, GMAIL_SCOPES)
      creds = flow.run_local_server(port=0)

    with open(token_path, "w") as token_file:
      token_file.write(creds.to_json())
  
  return build("gmail", "v1", credentials=creds)

class Status(Enum):
  NEW = "NEW"
  DRAFTED = "DRAFTED"
  SCHEDULED = "SCHEDULED"
  SENT = "SENT"
  FAILED = "FAILED"

def collect_rows():
  # connect to google sheets and grab sheet
  client = gspread.service_account(filename=SERVICE_ACCOUNT_PATH)
  spreadsheet = client.open(SHEET_NAME)
  sheet = spreadsheet.sheet1
  # returns rows in dict
  rows = sheet.get_all_records()

  scheduler_sheet = spreadsheet.get_worksheet(1)
  scheduler = scheduler_sheet.get_all_records()

  return rows, scheduler

# This will throw a custom error, just let it
def check_email(email):
  email_info = validate_email(email, check_deliverability=True)

  return email_info.normalized

def validate_contact(row):
    # Check contact rows
  columns = ["Company", "FirstName", "LastName", "Email"]

  for col in columns:
    if col not in row:
      raise Exception(f"Column {col} does not exist on this row.")
    
    value = row[col]
    
    if not isinstance(value, str):
      raise Exception(f"Value of column {col} must be string, got {type(value)}.")
    
    if len(value) == 0:
      raise Exception(f"Value of column {col} is empty.")
  
  email = row["Email"]

  normalized_email = check_email(email)

  row["Email"] = normalized_email

  return row

def validate_row(row):
  validated_contact_row = validate_contact(row)

  status = validated_contact_row["Status"]

  if not status:
    status = Status.NEW.value
  
  try:
    validated_contact_row["Status"] = Status(status)
  except ValueError:
    raise Exception(f"Invalid status in sheet: {status}")
  
  return validated_contact_row

"""
Ok, here's the plan:
We're planning on 20 emails a day during particular periods, but we also have to wait on approval
We need to keep track of how many emails have been scheduled for that day
Also, if there are approved emails waiting, we need to add those to the scheduled emails

Ok, here's the workflow:
NEW:
Process contact info w/ validation, and have it drafted up. Send the email as a draft 
and have it standing by, inputting draft id to keep track of it.
Switch to DRAFTED
DRAFTED:
Check if ApproveSend is good to go. If not, just keep it pushing.
Otherwise, schedule the email by assigning it the next available time slot.
Switch to SCHEDULED
SCHEDULED:
Check if currentTime > scheduledTime. If not, skip.
If yes, then send out the email by grabbing the draftID.


As for time slots, here's the current system.
We're going to send between CST 8:00AM - 2:00PM
For every scheduler 
"""

def validate_scheduler(scheduler):
  columns = ["NextSlotAtUTC", "AmountSent"]

  if len(scheduler) != 1:
    raise Exception(f"Expected number of rows: 1, Given: {len(scheduler)}")
  
  scheduler = scheduler[0]

  for col in columns:
    if col not in scheduler:
      raise Exception(f"Column {col} does not exist on scheduler row.")
  
  nextUTC = scheduler["NextSlotAtUTC"]

  if not nextUTC:
    scheduler["NextSlotAtUTC"] = datetime.now(timezone.utc).isoformat()
  
  dt = datetime.fromisoformat(nextUTC)

  if dt.tzinfo != timezone.utc:
    raise Exception("Read timestamp does not correspond to UTC timezone")

def main():
  try:
    rows, scheduler = collect_rows()
    validate_scheduler(scheduler)
    print(rows)
    print(scheduler)
  except Exception as e:
    logging.exception(e)
    return
  
  # for row in rows:
  #   try:
  #     row = validate_row(row)

  #     status = row["Status"]


  #   except Exception as e:
  #     logging.exception(e)
  #     print(e)
  #     continue


  # first_row = rows[0]
  # recipient = first_row.get("Email")
  # if not recipient:
  #   print("First row is missing Email; cannot create draft.")
  #   print(first_row)
  #   return

  # first_name = (first_row.get("FirstName") or "").strip() or "there"  # type: ignore
  # company = (first_row.get("Company") or "").strip() or "your company"  # type: ignore

  # body = email_creator(
  #   contact_first_name=first_name,
  #   officer_name="Ricardo Trevizo",
  #   company_name=company,
  # )

  # subject = f"CougarCS x {company} - Partnership Opportunity"

  # gmail_service = get_gmail_service()
  # draft = create_draft(gmail_service, recipient, subject, body)


if __name__ == "__main__":
  main()