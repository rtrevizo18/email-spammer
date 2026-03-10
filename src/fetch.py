import requests
import time
import json
import os
import random
from dotenv import load_dotenv

load_dotenv()

FIELDS = [
  "id",
  "name",
  "website",
  "all_locations",
  "one_liner",
  "industry",
  "team_size",
  "tags",
  "batch",
  "status"
]

# You can fetch it from the YC website
ALGOLIA_APP_ID = os.getenv("ALGOLIA_APP_ID")
ALGOLIA_API_KEY = os.getenv("ALGOLIA_API_KEY")

DATA_FILE = 'data.jsonl'

CHECKPOINT_FILE = "checkpoint.json"

def load_checkpoint():
  if os.path.exists(CHECKPOINT_FILE):
    with open(CHECKPOINT_FILE) as f:
      return json.load(f)["page"]
  return 0

def save_checkpoint(page):
  with open(CHECKPOINT_FILE, "w") as f:
    json.dump({"page": page}, f)

def clean_company(company):
  return {k: company.get(k) for k in FIELDS}


def fetch_page(page: int):
  """
  page: 0-indexed pagination
  """
  url = "https://45bwzj1sgc-dsn.algolia.net/1/indexes/*/queries"

  for attempt in range(3):
    try:
      headers = {
        "x-algolia-agent": "Algolia for JavaScript (3.35.1); Browser; JS Helper (3.16.1)",
        "x-algolia-application-id": ALGOLIA_APP_ID,
        "x-algolia-api-key": ALGOLIA_API_KEY,
        "content-type": "application/json"
      }

      payload = {
          "requests": [
              {
                  "indexName": "YCCompany_production",
                  "params": f"hitsPerPage=100&page={page}"
              }
          ]
      }

      r = requests.post(url, headers=headers, json=payload)

      return r
    except requests.RequestException:
      time.sleep(2 ** attempt + 5)

  raise RuntimeError(f"API failed too many times on page {page}")

def stream_api(start_page):
  page = start_page

  while True:
    data = fetch_page(page)

    if not data:
      break

    yield page, data
    page += 1
  

if __name__ == '__main__':
  start_page = load_checkpoint()
  with open(DATA_FILE, 'a') as f:
    for page, response in stream_api(start_page):
      companies = response.json()['results'][0]['hits']
      batch = ""
      for company in companies:
        cleaned_comp = clean_company(company)
        batch += json.dumps(cleaned_comp) + '\n'
      f.write(batch)
      # We finished `page` page, so checkpoint should now be next page
      save_checkpoint(page + 1)
      seconds = random.random() * 5 + 5
      print(f"Wrote to {DATA_FILE}. Waiting {seconds} seconds.")
      time.sleep(seconds)