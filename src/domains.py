import pandas as pd
from urllib.parse import urlparse

DATA_FILE = "domains.jsonl"
data = pd.read_json(DATA_FILE, lines=True)

def get_domain(url):
  parsed = urlparse(url)
  return parsed.netloc.replace("www.", "")


scraped_domains = data['website'].apply(get_domain)

email_pattern = r'^[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$'

invalid_mask = scraped_domains.isnull() | (scraped_domains == "") | ~scraped_domains.str.contains(email_pattern)

cleaned_data = data[~invalid_mask]

cleaned_data['domain'] = scraped_domains[~invalid_mask]

cleaned_data.to_json(DATA_FILE, orient='records', lines=True)