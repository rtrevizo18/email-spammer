import os
import dotenv
from jinja2 import Template
import base64
import gspread
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

template = Template("""
Hi {{first_name}},

I hope this email finds you well! My name is {{officer}}, and I'm the Corporate Relations Director for the University of Houston's largest Computer Science student organization, CougarCS.

CougarCS is an ACM chapter organization committed to the professional development and academic success of our 200+ active members. We provide various services to our students, including company-sponsored career readiness workshops, personalized tutoring sessions, and a wide library of open-source projects built and maintained by our members. We've worked with companies such as Google, Microsoft, and Apple, and have partnered with over 50 companies to bring exciting events for our members. Additionally, we host CodeRED, the largest hackathon at UH.

As a sponsor, {{company}} will have access to several CougarCS perks, such as candid facetime with experienced student developers, extensive brand recognition marketing through our social media platforms, and a live environment where users can test your product and provide direct feedback. {{company}} can expect no less than a multitude of accommodations and recruitment opportunities from our team!

I would love to set up a quick chat to discuss a potential partnership between CougarCS and {{company}}. If you would like to learn more about our organization, please refer to our website:
      
cougarcs.com

Thank you for your time! We look forward to hearing from you soon.

Best regards,
{{officer}}, CougarCS Corporate Relations
""")
def email_creator(contact_first_name, officer_name, company_name):
  body = template.render(
    first_name=contact_first_name,
    officer=officer_name,
    company=company_name
  )

  return body

def create_draft(service, to, subject, body):
  message = f"To: {to}\r\nSubject: {subject}\r\n\r\n{body}"

  encoded = base64.urlsafe_b64encode(message.encode()).decode()

  draft = {
    'message': {
      'raw': encoded
    }
  }

  return service.users().drafts().create(userId="me", body=draft).execute()


dotenv.load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

scope = [
  "https://www.googleapis.com/auth/spreadsheets",
  "https://www.googleapis.com/auth/drive"
]

GMAIL_SCOPES = [
  "https://www.googleapis.com/auth/gmail.compose"
]

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

    # Persist OAuth token for future runs.
    with open(token_path, "w") as token_file:
      token_file.write(creds.to_json())
  
  return build("gmail", "v1", credentials=creds)


def main():
  sheet_name = os.getenv("SHEET_NAME", "Spring 2026 Email Spammer")
  sheet_tab = os.getenv("SHEET_TAB", "sheet1")
  service_account_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")

  client = gspread.service_account(filename=service_account_path)
  spreadsheet = client.open(sheet_name)
  sheet = spreadsheet.sheet1

  rows = sheet.get_all_records()
  if not rows:
    print("No rows found in sheet.")
    return

  first_row = rows[0]
  recipient = (first_row.get("Email") or "").strip()  # type: ignore
  if not recipient:
    print("First row is missing Email; cannot create draft.")
    print(first_row)
    return

  first_name = (first_row.get("FirstName") or "").strip() or "there"  # type: ignore
  company = (first_row.get("Company") or "").strip() or "your company"  # type: ignore

  body = email_creator(
    contact_first_name=first_name,
    officer_name=os.getenv("OFFICER_NAME", "Ricardo Trevizo"),
    company_name=company,
  )
  subject = os.getenv("EMAIL_SUBJECT", f"Partnership Opportunity - {company}")

  gmail_service = get_gmail_service()
  draft = create_draft(gmail_service, recipient, subject, body)

  print(f"Draft created for {recipient}")
  print(f"Draft ID: {draft.get('id')}")


if __name__ == "__main__":
  main()