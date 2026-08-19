# -*- coding: utf-8 -*-
import io, statistics
rows=[]
for l in io.open('ct_flat.txt', encoding='utf-8-sig'):
    l=l.rstrip('\n').rstrip('\r')
    if not l: continue
    p=l.split('|')
    if len(p)<4: continue
    try:
        v=int(p[1]); d=int(p[2])
    except: continue
    rows.append((v,d,p[0],'|'.join(p[3:])))
rows.sort(reverse=True)
print('TOP 12')
for r in rows[:12]:
    print(r[2], r[0], r[1], r[3][:90].encode('ascii','ignore').decode())
print('BOTTOM 12')
for r in rows[-12:]:
    print(r[2], r[0], r[1], r[3][:90].encode('ascii','ignore').decode())
print('n=',len(rows),'median=',statistics.median([r[0] for r in rows]))
