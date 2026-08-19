# -*- coding: utf-8 -*-
import io, os, re, sys
T = r"research/reference/courtroomtime/txt"
P = re.compile(r"why (are|did|would|do|don't|didn't|is|was|aren't|were) you|i don'?t know why|stop interrupting|let me finish|excuse me|in cuffs|handcuff|out of the courtroom|take (her|him) into custody|for the youtube|do me a favor|are you serious|i'?m not going to lie|guess what|i thought so|nonsense|disrespect|why shouldn'?t i|those are your|listen to me|i'?ma interrupt|calm down|take a breath|hold on|sit down|no ma'?am|be quiet|you understand me|last time|attitude|ridiculous|really\?|contempt|foolish|grown|acting like|come on now|mhm", re.I)
for v in sys.argv[1:]:
    print("="*24, v)
    ls = io.open(os.path.join(T, v+'.txt'), encoding='utf-8').read().split('\n')
    for i, l in enumerate(ls):
        if P.search(l):
            print(l.replace('&gt;','>'))
    print()
