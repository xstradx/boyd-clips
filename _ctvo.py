# -*- coding: utf-8 -*-
import io, os, re
T = r"research/reference/courtroomtime/txt"
WIN = "ERPX6JpX5OU _-WRN7q01OY rcub_Jev9NE 6Tp2eiBjGB8 urZza-9kdP0 ePdAxp1Zs8Y aH0fnO4w-dg lfAlCDsEQZ4".split()
LOS = "q1Fo7x_0ItI bQjZEqsESqE xUmB4XrFi3g 9ab4YTSQI-8 RfF0ouKeE0w 79nw7lP0jm0".split()
VO = re.compile(r"welcome back to courtroom time|let'?s dive in|let'?s find out|let'?s see what happens|don'?t forget to like|hit the notification|stay tuned|grab your popcorn|here are the top|these are the top|oh boy|did you catch that|wow this part|and there it is|hold up this is where|this is such a layered|let'?s be real|stay updated|see you next time|like comment and share|top (three|four|five|six|3|4|5|6)", re.I)
GW = re.compile(r"guess what", re.I)
MH = re.compile(r"\bmhm\b|\bmm-?hmm\b", re.I)
def firstvo(ls):
    for l in ls:
        if VO.search(l):
            m = re.match(r"\[(\d+):(\d+)\]", l)
            return int(m.group(1))*60+int(m.group(2)) if m else -1
    return None
for grp, ids in (('WIN',WIN),('LOS',LOS)):
    for v in ids:
        ls = io.open(os.path.join(T, v+'.txt'), encoding='utf-8').read().split('\n')
        txt = '\n'.join(ls)
        nvo = len([l for l in ls if VO.search(l)])
        print(grp, v, 'lines=%d' % len(ls), 'VOhits=%d' % nvo, 'firstVOsec=%s' % firstvo(ls),
              'guesswhat=%d' % len(GW.findall(txt)), 'mhm=%d' % len(MH.findall(txt)))
