# GATES — short EDIT variants, so Nathan can pick from real examples

2026-09-03. He asked for all four caption treatments and all four cutaway
treatments, built, not described: *"lets try all and then i could pick"* /
*"all of them. we need to see examples"*.

Reference corpus is HIS OWN top six shorts (no other channel has a
successful Judge Boyd short — measured, 6 results, top one a paintball
teaser). Downloaded to `D:/Boyd Clips/research/shorts/`:

    865,000  sp3IXJYBFwY  48.5s   mostly B-roll, dated news cards
     61,000  dAI3GNmNt_s  58.3s   word-by-word + coloured keyword box
     39,000  upjOR9Tr0P8  58.5s   outside cutaway, "FULL VIDEO OUT NOW" + arrow
     27,000  oJvViwEhFyk  57.3s   word-by-word, keyword box, CTA card
     22,000  Usxub-MQm9k  59.5s   emoji graphics, keyword box
     16,000  Zl0i8N8botY  57.9s   word-by-word, CTA card

Base span for every variant: the PERKINS stolen-gun scene already built and
gated — `--seg 5400.2:5419.6 --seg 5420.3:5450.9` on `QzcSk3BNYqI`.
Holding the span FIXED is the point: only the edit treatment varies, so his
pick is about the treatment and nothing else.

SCOPE: nothing is posted. Publishing stays a hard stop.

---

## Phase 1 — caption treatments (4 variants)

- [ ] G1  Four caption variants render, from the same span, to four files
      CHECK: `node -e "const fs=require('fs');const d='D:/Boyd Clips/shortwork/CAPVAR';const v=['A_winners','B_wordonly','C_phrase_key','D_karaoke'];const miss=v.filter(x=>!fs.existsSync(d+'/PERKINS_CAP_'+x+'.mp4'));console.log(miss.length?'MISSING '+miss.join(','):'CAPVAR_ALL_PRESENT')"`
      EXPECT: CAPVAR_ALL_PRESENT

- [ ] G2  The four are genuinely different renders, not four copies
      CHECK: `python tools/_capvar_check.py --distinct`
      EXPECT: CAPVAR_DISTINCT_OK
      (byte-hash of each .ass AND mean |pixel diff| between variants in the
      caption band > 2.0; four identical files is the failure this catches)

- [ ] G3  Variant A matches his winners' card length: <= 2 words per card
      CHECK: `python tools/_capvar_check.py --cards A_winners --max-words 2`
      EXPECT: CARDS_OK

- [ ] G4  Variant A actually draws a coloured highlight box behind the key word
      CHECK: `python tools/_capvar_check.py --keybox A_winners`
      EXPECT: KEYBOX_OK
      (counts saturated non-white pixels inside the caption band; the CONTROL
      is variant B, which must FAIL the same check — an absence check that has
      never been seen to fail is not evidence)

- [ ] G5  No variant draws a word before it is spoken (R34 reveal, existing gate)
      CHECK: `python tools/_capvar_check.py --reveal-all`
      EXPECT: REVEAL_ALL_OK

- [ ] G6  Every oracle above is proved against a known-bad control before it counts
      CHECK: `python tools/_capvar_check.py --selftest`
      EXPECT: CAPVAR_SELFTEST_OK

- [ ] G7  A side-by-side contact sheet exists, four variants at the same timestamps
      CHECK: `node -e "const fs=require('fs');const p='D:/Boyd Clips/shortwork/CAPVAR/_CAPTION_VARIANTS.jpg';console.log(fs.existsSync(p)&&fs.statSync(p).size>200000?'SHEET_OK':'SHEET_MISSING')"`
      EXPECT: SHEET_OK

- [ ] G8  MANUAL — I have opened the sheet at 100% and can say what differs in
      each variant in my own words before it is shown to him (R52 discipline,
      applied to my own builds against each other).

## Phase 2 — cutaway treatments (4 variants)

- [ ] G9  Four cutaway variants render from the same span
      CHECK: `node -e "const fs=require('fs');const d='D:/Boyd Clips/shortwork/CUTVAR';const v=['A_mugshot_cards','B_full_broll','C_datecards','D_courtroom_only'];const miss=v.filter(x=>!fs.existsSync(d+'/PERKINS_CUT_'+x+'.mp4'));console.log(miss.length?'MISSING '+miss.join(','):'CUTVAR_ALL_PRESENT')"`
      EXPECT: CUTVAR_ALL_PRESENT

- [ ] G10 Every non-courtroom frame used is sourced and listed, with where it
      came from — no invented or unattributed imagery
      CHECK: `python tools/_capvar_check.py --sources`
      EXPECT: SOURCES_OK

- [ ] G11 Variant D (courtroom only) contains no cutaway — the negative control
      for G9/G10 and proof the cutaway detector can distinguish them
      CHECK: `python tools/_capvar_check.py --cutaway-count`
      EXPECT: CUTAWAY_COUNTS_OK

- [ ] G12 A contact sheet exists for the cutaway variants
      CHECK: `node -e "const fs=require('fs');const p='D:/Boyd Clips/shortwork/CUTVAR/_CUTAWAY_VARIANTS.jpg';console.log(fs.existsSync(p)&&fs.statSync(p).size>200000?'SHEET_OK':'SHEET_MISSING')"`
      EXPECT: SHEET_OK

- [ ] G13 MANUAL — both sheets are shown to him IN THE CHAT as images, not as
      paths, and the differences are named. He picks; nothing is posted.

---

## Not gated, said out loud

- Whether any variant is actually GOOD is his call. These gates prove the four
  are built, are different, and do what they claim — never that one wins.
- The 57-59.5s length of his winners is a separate change from the caption and
  cutaway treatment; it is NOT varied here, so all variants stay at the base
  span's length and the comparison stays clean.
- Phase 2 depends on what imagery is actually reachable for PERKINS. If a
  variant cannot be sourced honestly it gets ABANDON with the reason, not a
  faked frame.
