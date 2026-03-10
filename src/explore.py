import pandas as pd
import json

DATA_FILE = "data.jsonl"
data = pd.read_json(DATA_FILE, lines=True)

print(data)