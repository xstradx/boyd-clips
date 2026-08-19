import os
SUB = r"C:\Users\natha\Projects\boyd-clips\research\reference\courtroomtime\subs"
v = [f for f in os.listdir(SUB) if f.endswith(".vtt")]
print("vtt files:", len(v))
