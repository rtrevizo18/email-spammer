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

TOTAL_AMOUNT_PER_DAY = 20

def validate_scheduler(scheduler):
  columns = ["NextSlotAtUTC", "AmountSent", "Officer", "Role"]

  if len(scheduler) != 1:
    raise Exception(f"Expected number of rows: 1, Given: {len(scheduler)}")
  
  scheduler_row = scheduler[0]

  for col in columns:
    if col not in scheduler_row:
      raise Exception(f"Column {col} does not exist on scheduler row.")
  
  nextUTC = scheduler_row["NextSlotAtUTC"]

  if not nextUTC:
    scheduler_row["NextSlotAtUTC"] = datetime.now(timezone.utc).isoformat()
  
  dt = datetime.fromisoformat(nextUTC)

  if dt.tzinfo != timezone.utc:
    raise Exception("Read timestamp does not correspond to UTC timezone.")
  
  amount_sent = scheduler_row["AmountSent"]

  if not isinstance(amount_sent, int):
    raise Exception("AmountSent is not a number.")
  
  officer_name = scheduler_row["Officer"]

  if not isinstance(officer_name, str) or len(officer_name) == 0:
    raise Exception("Officer name is a string.")
  
  officer_role = scheduler_row["Role"]

  if not isinstance(officer_role, str) or len(officer_role) == 0:
    raise Exception("Officer role is a string.")

  return dt, amount_sent, officer_name, officer_role

def create_draft(service, to, subject, body):
  message = f"To: {to}\r\nSubject: {subject}\r\n\r{body}"

  encoded = base64.urlsafe_b64encode(message.encode()).decode()

  draft = {
    'message': {
      'raw': encoded
    }
  }

  return service.users().drafts().create(userId="me", body=draft).execute()

def send_draft(service, draft_id):
    try:
        sent_message = service.users().drafts().send(
            userId="me",
            body={
                "id": draft_id
            }
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

def get_spreadsheet():
  client = gspread.service_account(filename=SERVICE_ACCOUNT_PATH)
  spreadsheet = client.open(SHEET_NAME)
  return spreadsheet


def collect_rows(spreadsheet):
  # connect to google sheets and grab sheet

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

def process_new_row(gmail_service, sheet, row, officer_name, officer_role):
  first_name = row["FirstName"]
  company = row["Company"]
  email = row["Email"]

  subject, body = email_creator(
    contact_first_name=first_name,
    company=company,
    officer_name=officer_name,
    officer_role=officer_role
  )

  draft = create_draft(gmail_service, email, subject, body)
  print(draft)

  row_number = row["ID"] + 1
  draft_id = draft["id"]

  worksheet = sheet.worksheet("Sheet1")

  cell = f"I{row_number}"

  worksheet.update([[draft_id]], cell)

  cell = f"F{row_number}"

  worksheet.update([["DRAFTED"]], cell)

def process_drafted_row(gmail_service, row):
  approve_send = row.get("ApproveSend")

  if approve_send == "FALSE":
    return 0
  # Let's assume it's true fuck it
  id = row["GID"]

  send_draft(gmail_service, id)

  return 1


def main():
  try:
    sheet = get_spreadsheet()
    rows, scheduler = collect_rows(sheet)
    next_time, amount_sheet, officer_name, officer_role = validate_scheduler(scheduler)
    # print(rows)
    # print(scheduler)
  except Exception as e:
    logging.exception(e)
    return
  
  try:
    gmail_service = get_gmail_service()
  except Exception as e:
    logging.exception(e)
    return
  
  # If amount sent is over TOTAL_AMOUNT_PER_DAY 
  if amount_sheet >= TOTAL_AMOUNT_PER_DAY: 
    # If it's same day, gtfo
    if next_time.date() == datetime.now().date():
      return
    # If its not, start that thing! 
    amount_sheet = 0
  
  
  for row in rows:
    try:
      row = validate_row(row)

      status = row["Status"]

      if status == Status.NEW:
        process_new_row(gmail_service, sheet, row, officer_name, officer_role)
        return
      elif status == Status.DRAFTED:
        amount_sheet += process_drafted_row(gmail_service, row)
        return


    except Exception as e:
      print(e)
      # Let's just increment cause I'm scared lol
      amount_sheet += 1
      return

if __name__ == "__main__":
  main()