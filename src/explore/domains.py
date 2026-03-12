import pandas as pd
from urllib.parse import urlparse




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


if __name__ == '__main__':
  fortune_500_explore()