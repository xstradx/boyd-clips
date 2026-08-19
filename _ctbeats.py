# -*- coding: utf-8 -*-
import io, os, re, sys
T = r"research/reference/courtroomtime/txt"
WIN = "ERPX6JpX5OU _-WRN7q01OY rcub_Jev9NE 6Tp2eiBjGB8 urZza-9kdP0 ePdAxp1Zs8Y aH0fnO4w-dg lfAlCDsEQZ4".split()
LOS = "q1Fo7x_0ItI bQjZEqsESqE xUmB4XrFi3g 9ab4YTSQI-8 RfF0ouKeE0w 79nw7lP0jm0".split()

BEATS = {
 'boyd_scolds_why': r"\bwhy (are|did|would|do|don't|didn't|is|was|aren't|were) you\b|\bwhy do people\b|\bwhy would (somebody|someone|anybody|people)\b",
 'dont_understand': r"i (don't|do not) understand why|i don't know why (people|someone|somebody|anybody|attorneys|you)",
 'shutdown_interrupt': r"stop interrupting|let me finish|excuse me,? (stop|no)|i'?m?a? interrupt you|do not interrupt|listen to me|let me speak|i'?m talking",
 'ejection_cuffs': r"in cuffs|handcuffs on|put (her|him|them) in the box|out of the courtroom|take (her|him|them) into custody|going into custody|be taken into custody|remand",
 'sarcasm_mock': r"for the youtube|do me a favor|are you serious|really\?|i'?m not going to lie to you|guess what|i thought so|congratulat|i like you|good luck to you|let's be honest",
 'threat_prison': r"you'?re looking at|i will send you to prison|why shouldn'?t i send you to prison|those are your (only )?two choices|i'?ll give you \d+ years",
 'def_argues_back': r"(that'?s )?not (exactly )?true|respectfully,? (your|judge)|no,? it isn'?t|yes it is|i disagree|that'?s a lie|but i|i have to ask you|i'?m trying to make a record|asking for record",
 'def_cries_begs': r"please don'?t|i'?m (so |really )?sorry|i apolog|another chance|forgive|i'?m scared|i beg",
 'family_speaks': r"\bmy mom\b|\bmy mother\b|his mother|her mother|\bmom,? |grandchild|my son\b|my daughter\b",
 'lie_caught': r"you'?re not telling|that'?s not (what|true)|i don'?t believe|you said you|you told me|so let'?s be honest|hearsay|proof",
}
def scan(v):
    txt = io.open(os.path.join(T, v+'.txt'), encoding='utf-8').read().lower()
    txt = txt.replace('&gt;','>')
    n = {}
    for k, p in BEATS.items():
        n[k] = len(re.findall(p, txt))
    n['_words'] = len(txt.split())
    return n
print('id\t' + '\t'.join(list(BEATS.keys())+['words']))
for grp, ids in (('WIN',WIN),('LOS',LOS)):
    tot = {}
    for v in ids:
        n = scan(v)
        print(grp, v, '\t'.join(str(n[k]) for k in list(BEATS.keys())+['_words']))
        for k in n: tot[k] = tot.get(k,0)+n[k]
    print(grp, 'TOTAL', '\t'.join(str(tot[k]) for k in list(BEATS.keys())+['_words']))
    print(grp, 'PER10K', '\t'.join('%.1f'%(tot[k]*10000.0/tot['_words']) for k in BEATS.keys()))
    print()
