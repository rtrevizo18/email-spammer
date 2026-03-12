import pandas as pd
from urllib.parse import urlparse
import requests
import logging

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
  try:
    r = requests.get(url, params=params, allow_redirects=True)

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

print(lucky_search("nintendo"))