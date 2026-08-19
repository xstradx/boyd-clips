import os, time
SUB = r"C:\Users\natha\Projects\boyd-clips\research\reference\courtroomtime\subs"
c = lambda: len([f for f in os.listdir(SUB) if f.endswith(".vtt")])
prev, still = c(), 0
for _ in range(9):
    time.sleep(5)
    n = c()
    still = still + 1 if n == prev else 0
    prev = n
print("vtt", prev, "unchanged_polls", still)
