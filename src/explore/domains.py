import pandas as pd
from urllib.parse import urlparse
import requests
import logging
import time
import json
import random
import os


random.seed(1234)

logger = logging.getLogger(__name__)



def yc_domain_explore():
  DATA_FILE = "datasets/data.jsonl"
  RESULT_FILE = "datasets/yc_domains.jsonl"
  data = pd.read_json(DATA_FILE, lines=True)

  def get_domain(url):
    parsed = urlparse(url)
    return parsed.netloc.replace("www.", "")


  scraped_domains = data['website'].apply(get_domain)

  email_pattern = r'^[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$'

  invalid_mask = scraped_domains.isnull() | (scraped_domains == "") | ~scraped_domains.str.contains(email_pattern)

  cleaned_data = data[~invalid_mask]

  cleaned_data['domain'] = scraped_domains[~invalid_mask]

  cleaned_data.to_json(RESULT_FILE, orient='records', lines=True)

def fortune_500_explore():
  DATA_FILE = "datasets/fortune500.csv"
  RESULT_FILE = "datasets/fortune500_domains.jsonl"

  data = pd.read_csv(DATA_FILE)

  # all data is of format 'website.tld', checked

  domain_data = data['Website']

  email_pattern = r'^[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$'

  invalid_mask = domain_data.isnull() | (domain_data == "") | ~domain_data.str.contains(email_pattern)

  cleaned_data = data[~invalid_mask]

  cleaned_data.to_json(RESULT_FILE, orient='records', lines=True)


def lucky_search(query):
  url = "https://www.google.com/search"

  params = {
    "q": query,
    "btnI": "I"
  }

  headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
  }

  try:
    r = requests.get(url, params=params, allow_redirects=True, headers=headers)

    if not r.ok:
      raise Exception({
        "status_code": r.status_code,
        "message" : r.reason,
        "on_request" : r.request
      })

    scraped_url = r.url

    intermed_url = urlparse(scraped_url).query.split('=')[1]

    parsed = urlparse(intermed_url)

    domain = parsed.netloc.replace("www.", "")

    return domain
  except Exception as e:
    print(e)
    logger.error(e)
    raise e

def load_houston_and_fetch():
  DATA_FILE = "datasets/houston.csv"
  RESULT_FILE = "datasets/houston_domains.jsonl"
  CHECKPOINT_FILE = "datasets/houston_checkpoint.jsonl"

  data = pd.read_csv(DATA_FILE)
  companies = data['Company']

  processed = {}
  if os.path.exists(CHECKPOINT_FILE):
    with open(CHECKPOINT_FILE, "r") as f:
      for line in f:
        entry = json.loads(line)
        processed[entry["Company"]] = entry["domain"]
  
  results = []

  for company in companies:
    if company in processed:
      domain = processed[company]
    else:
      domain = lucky_search(f"{company} offical website")
      with open(CHECKPOINT_FILE, "a") as f:
        f.write(json.dumps({"Company": company, "domain": domain}) + "\n")
      time.sleep(random.uniform(35, 45))
    results.append(domain)

  
  data['domain'] = results

  data.to_json(RESULT_FILE, orient='records', lines=True)

  os.remove(CHECKPOINT_FILE)

if __name__ == '__main__':
  load_houston_and_fetch()