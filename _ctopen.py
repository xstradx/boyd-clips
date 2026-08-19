# -*- coding: utf-8 -*-
import io, os
T = r"research/reference/courtroomtime/txt"
ids = "rcub_Jev9NE 6Tp2eiBjGB8 urZza-9kdP0 ePdAxp1Zs8Y aH0fnO4w-dg lfAlCDsEQZ4".split()
for v in ids:
    print("="*20, v)
    ls = io.open(os.path.join(T, v+'.txt'), encoding='utf-8').read().split('\n')
    for l in ls[:9]:
        print(l)
    print()
