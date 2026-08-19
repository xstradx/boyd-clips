import os, json
from PIL import Image
D = os.path.dirname(os.path.abspath(__file__)); TH = os.path.join(D, "thumbs")
meta = json.load(open(os.path.join(D, "thumbmeta.json"), encoding="utf-8"))
for grp, cols in (("top", 3), ("bot", 2)):
    fs = [m for m in meta if m["grp"] == grp]
    tw, th = 640, 360
    rows = (len(fs)+cols-1)//cols
    sheet = Image.new("RGB", (cols*tw, rows*th), (30, 30, 30))
    for i, m in enumerate(fs):
        im = Image.open(os.path.join(TH, m["file"])).convert("RGB").resize((tw, th))
        sheet.paste(im, ((i % cols)*tw, (i//cols)*th))
    p = os.path.join(D, f"sheet_{grp}.jpg"); sheet.save(p, quality=88)
    print(p, sheet.size, len(fs))
