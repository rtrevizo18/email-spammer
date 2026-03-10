import random
import time

# Fetch 30 pages of data
for i in range(30):
  print(f"Fetching {i}th iteration of data")


  seconds = random.randint(0, 10) + 2
  print(f"Waiting for {seconds} second(s)")
  time.sleep(seconds)