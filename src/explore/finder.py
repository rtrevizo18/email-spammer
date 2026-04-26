import requests
import dotenv
import os
import json
from bs4 import BeautifulSoup

dotenv.load_dotenv()

SERP_API_KEY = os.getenv("SERP_API_KEY")

def google_search(q):
  url = "https://serpapi.com/search.json"

  params = {
    "engine": "google",
    "q": q,
    "location": "United States",
    "google_domain": "google.com",
    "hl": "en",
    "gl": "us",
    "api_key" : SERP_API_KEY
  }

  response = requests.get(url, params=params)

  data = response.json()

  return json.dumps(data)


def bruh(query):
  url = "https://www.google.com/search"

  params = {
    "q": query,
  }

  headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
  }

  res = requests.get(url, params=params, headers=headers)

  soup = BeautifulSoup(res.text, "html.parser")

  for a in soup.select("a"):
    link = a.get("href")
    if link and "linkedin.com/in" in link:
      print(link)

if __name__ == '__main__':
  bruh('site:linkedin.com/in "software engineer" Houston')