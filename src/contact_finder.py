import requests
import dotenv
import os

dotenv.load_dotenv()

HUNTER_API_KEY = os.getenv("HUNTERIO_API_KEY")

def hunter_contact(domain):

  url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={HUNTER_API_KEY}"
  r = requests.get(url).json()

  return r