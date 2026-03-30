import gspread
from google.oauth2.service_account import Credentials
import os
import dotenv

dotenv.load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

print(GOOGLE_API_KEY)

scope = [
  "https://www.googleapis.com/auth/spreadsheets",
  "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file("credentials.json", scopes=scope)


client = gspread.authorize(creds)

sheet = client.open("Spring 2026 Email Spammer").sheet1

data = sheet.get_all_records()
print(data)

new_row_data = ["Zayn", "Malik", 12, 20]

sheet.append_row(new_row_data)

print("Row added")