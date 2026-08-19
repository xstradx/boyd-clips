import os, json, sqlite3
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
c = sqlite3.connect("state/pipeline.db")
n = e = 0
for (p,) in c.execute("select payload from cases"):
    d = json.loads(p)
    n += 1
    if d.get("eligible"):
        e += 1
print("cases", n, "payload-eligible", e)
SUB = "research/reference/courtroomtime/subs"
print("vtt", len([f for f in os.listdir(SUB) if f.endswith('.vtt')]))
W = "work"
print("work dirs", len(os.listdir(W)) if os.path.isdir(W) else "none")
