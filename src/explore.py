import pandas as pd
import json


dataFrame = pd.DataFrame(json.load(open("data.json", encoding='utf8'))['results'][0]['hits'])
