import os, json, sqlite3
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
c = sqlite3.connect("state/pipeline.db")
c.row_factory = sqlite3.Row
print("total", c.execute("select count(*) from cases").fetchone()[0])
print("shortable", c.execute("select count(*) from cases where shortable=1").fetchone()[0])
print("safety_pass", c.execute("select count(*) from cases where safety_pass=1").fetchone()[0])
print("both", c.execute("select count(*) from cases where safety_pass=1 and shortable=1").fetchone()[0])
r = dict(c.execute("select * from cases where shortable=1 limit 1").fetchone())
for k, v in r.items():
    if k != "payload":
        print(" ", k, "=", str(v)[:200])
p = json.loads(r["payload"])
def walk(o, pre=""):
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, (dict, list)) and len(str(v)) > 200:
                print(pre + k + ":")
                walk(v, pre + "  ")
            else:
                print(pre + k, "=", str(v)[:260])
    elif isinstance(o, list):
        print(pre + "[list n=%d]" % len(o), str(o[:1])[:260])
walk(p)
print("VIDEO COUNT", c.execute("select count(distinct video_id) from cases").fetchone()[0])
