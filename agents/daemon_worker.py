
import time
import sys

print("[daemon] started")

while True:
    print("[daemon] alive")
    sys.stdout.flush()
    time.sleep(3)
