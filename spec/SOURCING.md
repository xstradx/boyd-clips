# SOURCING — music, stock footage, and the rights position

**All prices and clauses below were fetched on 2026-08-12.** Every figure carries
the URL it came from. Anything I could not fetch is marked **NOT VERIFIED**;
anything I inferred is marked **GUESS**. Nothing here is from memory.

Vendor pricing changes without notice. Re-check before any card is entered —
this file is a snapshot, not a live fact. Per the standing money rule: confirm
the charge and the balance on the vendor's own checkout before subscribing.

---

## 0. The four findings that actually matter

1. **Texas does not recognise false light.** The question as posed has no Texas
   cause of action behind it. The real exposure is **defamation by implication**,
   and the Texas Supreme Court's formulation of it names our exact fact pattern:
   *"juxtaposing facts in a misleading way."* See §3.

2. **Most stock libraries' licences prohibit the use this channel is made of.**
   Storyblocks and Envato Elements flatly bar using footage "in connection with"
   sensitive or unflattering subjects, with **no disclaimer cure**. Getty and
   Artlist permit it *if* you superimpose a disclaimer. This inverts the usual
   creator advice — Storyblocks is the popular pick and is the worst fit here.

3. **Videvo no longer exists.** `videvo.net` 301-redirects to Freepik, now
   rebranded Magnific. Verified by header trace on 2026-08-12 (§2).

4. **`SAFETY_RULES.md`'s "Clipping it is lawful" is not supported by any source
   I could fetch.** No Texas rule addresses reuse of an already-published court
   stream in either direction. Meanwhile the videos carry the **Standard YouTube
   License** (not Creative Commons), and OCA's own guidance tells judges that
   recording the stream "is not permitted and can be enforced with contempt". The
   likely first mover against a monetized channel is **YouTube's ToS**, not Bexar
   County. See §4 — this is the highest-stakes item in the document.

---

## 1. MUSIC

### 1.1 Price table

| Service | Plan | Price as displayed | Annual total | Source URL |
|---|---|---|---|---|
| YouTube Audio Library | — | free (no price shown; included in YouTube Studio) | $0 | support.google.com/youtube/answer/3376882 |
| Uppbeat | Free | `$0 /month` | $0 | uppbeat.io/pricing |
| Uppbeat | Essentials | `$6.99/month` — *"You're saving 20% with yearly billing"* | $83.88 **(COMPUTED)** | uppbeat.io/pricing |
| Uppbeat | Creator | `$8.99/month` (yearly) | $107.88 **(COMPUTED)** | uppbeat.io/pricing |
| Uppbeat | Pro | `$14.99/month` (yearly) | $179.88 **(COMPUTED)** | uppbeat.io/pricing |
| Epidemic Sound | Creator | `$9.99` — *"Per month, billed $119.88 yearly."* | $119.88 (quoted) | epidemicsound.com/pricing/ |
| Epidemic Sound | Pro | `$16.99` — *"Per month, billed $203.88 yearly."* | $203.88 (quoted) | epidemicsound.com/pricing/ |
| Epidemic Sound | Business | `$30` — *"Per month, billed $360 yearly."* | $360.00 (quoted) | epidemicsound.com/pricing/?plans=businesses |
| Artlist | Music & SFX | `Starting at $9.99/month` | ~$119.88 **(GUESS** — page does not state billing period on this tier**)** | artlist.io/page/pricing/max?tab=creative-assets |
| Artlist | Max | `$50.66/month` `Billed annually` | $607.92 **(COMPUTED)** | same |
| Artlist | Max Business | `$399/month` `Billed annually` | $4,788 **(COMPUTED)** | same |
| Musicbed | Individual — Unlimited Songs | `$29.99/month`, `Annual Subscription` | $359.88 **(COMPUTED)** | musicbed.com/pricing (behind "View Pricing" → "Youtube Creator / Podcaster") |
| Musicbed | Individual — Songs & SFX | `$39.98/month`, `Annual Subscription` | $479.76 **(COMPUTED)** | same |
| Soundstripe | Solo Creator | `$9.99/mo` ("starting price") | ~$119.88 **(GUESS)** | soundstripe.com/library/pricing |
| Soundstripe | Pro / Pro Plus / Business | price not rendered on the public page | **NOT VERIFIED** | same |
| Kevin MacLeod (incompetech) | CC BY 4.0 | free | $0 | incompetech.com/music/royalty-free/faq.html |
| Free Music Archive | per-track CC / CC0 | free | $0 | freemusicarchive.org/about |

> **Correction to an earlier read in this session:** an automated parse returned
> Uppbeat's tiers as "$699 / $899 / $1499 per month". That was a DOM-splitting
> artifact of `$6` + `99`. The real figures are **$6.99 / $8.99 / $14.99**,
> confirmed by rendering the page in a browser.

### 1.2 Does the licence survive channel monetization?

**YouTube Audio Library** — yes, explicitly:
> "If you're in the YouTube Partner Program, you can monetize videos with music
> and sound effects from the Audio Library."
> — support.google.com/youtube/answer/3376882

**Epidemic Sound** — yes, but capped by tier. The comparison table row reads
"Monetization — Publish and monetize content with our tracks, safe from
copyright claims", with `1 channel per platform` (Creator), `3` (Pro), `5`
(Pro Plus). Also:
> "there's no additional cost when you publish or monetize your content."

**Artlist** — yes, §7 "Monetize your Project in social media":
> "You can monetize up to 3 channels/accounts per platform and, with Teams plan,
> up to 5 channels/accounts per platform."
> — artlist.io/help-center/privacy-terms/artlist-license (Effective February 15, 2026)

**Uppbeat** — yes. Monetization is not restricted; the constraint is on *who you
are* (§4.3–4.6: Free and Essentials users "must be an individual or a
freelancer"). A solo-run channel qualifies.

**Musicbed** — yes, but the pricing page annotates it as
`Monetization (only in subscription)` on both Individual and Business tiers.
See §1.3 — this phrase and the licence terms do not obviously agree.

**Soundstripe** — the pricing page advertises "Automatically clear content claims
on YouTube" and `1 Channel` on Solo Creator.

### 1.3 What happens to already-published videos if the subscription lapses

**This is the clause that decides the recommendation.** Ranked best to worst.

**Uppbeat — strongest, and it is in the binding contract, not an FAQ.**
uppbeat.io/user-agreement, clause 6.4:
> "6.4 — Subject to your full compliance with this Agreement, notwithstanding the
> end of the Term, you may continue to use any Content in your Permitted Material
> in Permitted Media by Permitted Distribution provided that the first Permitted
> Distribution of such Permitted Content took place during the Term."

And separately, the safelist itself persists — clause 11.3.5:
> "11.3.5 — Any videos uploaded to your Safelisted Channels during the duration of
> your Paid Subscription and before the Subscription End Date will continue to be
> protected from YouTube Copyright Claims."

That second clause is the one nobody else writes down, and it is precisely the
"six months out" failure mode.

**Artlist — equally strong, §2 "Your Projects are yours to use Forever":**
> "Once you create Projects using downloaded Assets and publish them in any media
> during your subscription term, you can keep using your Projects in the same
> media and monetize them forever, even after your subscription has expired."
> "You're covered to create and publish your Projects while your account is
> active. When your subscription expires, those Projects can remain published in
> any media, but any new projects will not be covered."

**Epidemic Sound — asserted, but only in an FAQ.** From the pricing page FAQ
"What happens to my content if I cancel?":
> "Your content remains as it is, with full copyright protection. Any content you
> publish while you have a free trial or plan is protected, even after you cancel."

⚠️ **NOT VERIFIED against the binding subscription terms.**
`epidemicsound.com/terms/subscription-terms/` returned **HTTP 404** on
2026-08-12. The only legal link exposed from the pricing page was
`epidemicsound.com/policy/v2/legal/`, which I did not retrieve. Treat the
survival promise as a marketing statement until the actual licence is read.

**Musicbed — ambiguous, and the two sources conflict.** The licence terms
(musicbed.com/license-terms) contain no "cancel"/"expire" survival clause for
subscriptions; §3 is a per-project sync clause:
> "3. Perpetual Rights Clause: Perpetual rights granted under this license apply
> only to the specific project, product, and usage details outlined in this
> agreement. Any use, adaptation, or repurposing beyond the original scope—
> regardless of when it occurs— will require a separate license. ... For clarity,
> in-context archival rights are granted, allowing the content to remain
> accessible as originally distributed (e.g., on a website or social platform),
> but not to be reused or promoted in new campaigns or formats."

But the pricing page labels monetization `(only in subscription)`. Read together,
the video may stay up but whether it may stay *monetized* after lapse is
unresolved. The words "monetiz", "SyncID" and "Content ID" do not appear anywhere
in the licence terms document. **Do not rely on Musicbed surviving a lapse
without written confirmation from them.**

**Storyblocks (for its audio) — §1.2 grants a "perpetual" licence; §5 only cuts
off *new* downloads.** See §2.3.

### 1.4 Content ID: automatic, or must you whitelist?

**Every paid service here requires you to register the channel. None of them are
automatic.** This is the most common creator mistake and it is why claims appear
weeks after upload.

- **YouTube Audio Library — the only genuinely automatic one:**
  > "Copyright-safe music and sound effects downloaded from the Audio Library
  > won't be claimed by a rights holder through the Content ID system."
  >
  > With the caveat: "Only music and sound effects from the Audio Library are
  > known to YouTube to be copyright-safe. YouTube is not responsible for issues
  > that arise from 'royalty-free' music and sound effects from YouTube channels
  > or other music libraries."

- **Artlist — manual clearlist, and lost revenue is not refunded:**
  > "If you don't add your channel or YouTube Projects URL to the clearlist, you
  > may receive claims from Artlist Ltd and will not be able to monetize your
  > videos or remove ads from them. Once you add your channel or YouTube Projects
  > URL to the clearlist, any claims from Artlist Ltd will be cleared and your
  > monetization will be restored. **Please note that you will not be reimbursed
  > for lost monetization for the period during which your channel or YouTube
  > Projects URL was not listed on the Clearlist.**"

- **Uppbeat — safelist, and no guarantee:**
  > "Safelist: The tool, available to Paid Subscribers, which prevents copyright
  > claims for Content on specified Safelisted Channels."
  >
  > "3.7 — In respect of YouTube use of each Music Track, we require that you
  > follow all of our directions, including use of the Credit (where appropriate)
  > to eliminate YouTube Copyright Claims. **Although we use all reasonable
  > efforts to ensure that you do not experience any YouTube Copyright Claims, we
  > make no representations, warranties or guarantees, whether express or
  > implied, that no such YouTube Copyright Claims will be experienced by you.**"

  Free-tier users must credit — it is a **material term**, clause 6.3:
  > "6.3 — If you are a Free User, you must ensure that the appropriate Credit is
  > given whenever you use any Music Track. This is a material term of this
  > Agreement."

- **Epidemic Sound — "Safelisting: Connect your channels to avoid copyright
  claims on your content", 1 / 3 / 5 / 10 / unlimited channels by tier.**

- **Soundstripe** — "Automatically clear content claims on YouTube", scoped to
  allowlisted channels.

- **Artlist and Envato both forbid you registering *their* content in Content ID:**
  Artlist §5: "you can't register or claim ownership of the Assets or the
  Projects (or otherwise make it available) through any content detection and/or
  registration system, such as YouTube's Content ID (CID), Facebook Rights
  Manager, etc."

- **Kevin MacLeod / CC BY 4.0:**
  > "Yes, AND you can monetize the videos. Be sure to credit me."
  > Attribution requirement: "a credit needs to be placed such that a person who
  > wants to know where the music came from should have no difficulty in finding
  > it."
  >
  > **Risk:** CC BY tracks are widely re-uploaded and third parties have
  > historically registered them in Content ID. There is no whitelist to file
  > and no counterparty to fix it. Disputes fall on us.

### 1.5 Restrictions specific to true-crime / legal / news content

No vendor names "true crime" or "news". Two clauses bite indirectly:

**Uppbeat, clause 4.1.2 — the sharpest one for this channel:**
> "4.1.2 — Not being defamatory, discriminatory, obscene, promoting hatred,
> violence or cruelty, involving adult material (unless expressly agreed by us
> via separate written agreement), or intimidating or humiliating any person."

A courtroom channel that names defendants is not automatically in breach — but
"humiliating any person" is a term Uppbeat gets to interpret, and clause 16.1
lets either party terminate on unremedied material breach.

**Storyblocks §2.2 bars *political* use outright** (see §2.3) — relevant if a
clip involves an elected official.

**Epidemic Sound** — nothing found on subject matter. Its only content-linked
limit found was ads (Pro and above).

---

## 2. STOCK FOOTAGE

### 2.1 Price table

| Service | Plan | Price as displayed | Annual total | Source URL |
|---|---|---|---|---|
| Pexels | — | free | $0 | pexels.com/license/ |
| Pixabay | — | free | $0 | pixabay.com/service/license-summary/ |
| Mixkit | Free licences | free | $0 | mixkit.co/license/ |
| **Videvo** | — | **defunct — redirects to Freepik/Magnific** | — | see §2.2 |
| Magnific (ex-Freepik) | Free / Premium / Premium+ / Pro | prices **NOT VERIFIED** | — | magnific.com/legal/terms-of-use |
| Storyblocks | Essentials | `$21 per month, billed annually` | $252 **(COMPUTED)** | storyblocks.com/pricing |
| Storyblocks | Unlimited All Access | `$30 per month, billed annually` | $360 **(COMPUTED)** | same |
| Storyblocks | Small Business | `$40 per month, billed annually` | $480 **(COMPUTED)** | same |
| Artgrid | — | **NOT VERIFIED** — Artlist folded footage into the Artlist "Max" plan; no standalone Artgrid pricing page was reachable | — | — |
| Artlist Max (includes footage) | Max | `$50.66/month` `Billed annually` | $607.92 **(COMPUTED)** | artlist.io/page/pricing/max |
| Envato Elements | Core | `$16.50/month billed annually or monthly for USD $39` | $198 **(COMPUTED)** | elements.envato.com/pricing |
| Envato Elements | Plus | `$39/month billed annually or monthly for USD $59` | $468 **(COMPUTED)** | same |
| Envato Elements | Ultimate | `$109/month billed annually or monthly for USD $169` | $1,308 **(COMPUTED)** | same |
| Adobe Stock | 10 credits/mo | `US$29.99/mo` | $359.88 **(COMPUTED)** | stock.adobe.com/plans |
| Adobe Stock | Unlimited + AI Studio | `US$129.99/mo` | $1,559.88 **(COMPUTED)** | same |

Adobe note: "videos cost 8–20 credits", so 10 credits/month buys roughly
**one clip a month** — Adobe Stock is not a viable B-roll source at that tier.

### 2.2 Videvo is gone — verified

```
$ curl -sI https://www.videvo.net/
HTTP/1.1 301 Moved Permanently
Date: Wed, 12 Aug 2026 08:03:16 GMT
location: https://www.freepik.com/videos
```
Following the chain in a browser lands on
`https://www.magnific.com/videos`, titled
*"Free Stock Video Footage HD and 4K Download | Magnific (formerly Freepik)"*.
Any guide still recommending Videvo is stale. Its old licence tiers
(Videvo Attribution / Videvo Standard) are no longer retrievable; the governing
document is now Magnific's.

### 2.3 The clause that actually decides this — "sensitive use"

Every library has one. **They split into two incompatible camps**, and the split
is the single most important thing in this document.

#### Camp A — permitted, *if* you caption it

**Getty Images** (the industry-standard formulation — quoted here as the
practitioner benchmark even though we are not buying Getty), gettyimages.com/eula:
> "**No Sensitive Use Without Disclaimer.** If you use content that features
> models or property in connection with a subject that would be unflattering or
> unduly controversial to a reasonable person (for example, sexually transmitted
> diseases), you must indicate: (1) that the content is being used for
> illustrative purposes only, and (2) any person depicted in the content is a
> model. For example, you could say: \"Stock photo. Posed by model.\" No
> disclaimer is required for content marked \"editorial\" or \"intended for
> editorial\" that is used in a non-misleading editorial manner."

**Artlist**, §5 — the same cure, in a subscription library we can actually afford:
> "If our clips are included in your Project, which has a subject that may be
> reasonably perceived as unflattering or controversial (such as an advertisement
> dealing with sexually transmitted infections), although we have the required
> releases, you can't intentionally portray the Asset or model where applicable
> in a negative way and **must indicate that the model has no connection to the
> Project's content (for example: stating the following: "Stock footage, posed by
> model")**."

#### Camp B — flatly prohibited, no cure offered

**Storyblocks**, storyblocks.com/license/individual-license — and note that §2.2
reaches *juxtaposition*, which is exactly our fact pattern:
> "2.2 **No Unlawful Use** : You may not use the Stock Files for any pornographic,
> political, defamatory, or otherwise unlawful purpose, **whether directly or in
> context or juxtaposition with other material or subject matter.**"
>
> "2.5 **No Sensitive Use** — Stock Files may not be used in connection with a
> subject that would be unflattering or unduly controversial to a reasonable
> person. and any such use is a material breach of this Agreement."

§2.5 is **not limited to footage containing people**. On its face, a shot of an
empty courthouse corridor used in a segment about a violent offence is "in
connection with a subject that would be ... unduly controversial". Storyblocks
is the most-recommended library for exactly this kind of channel and is, on the
text, the worst fit.

**Envato Elements**, help.elements.envato.com/.../Envato-Elements-License
(Last revised: December 8, 2025):
> "Acceptable use of Items: ... you can't use an Item in connection with material
> which is offensive, defamatory, pornographic, obscene or demeaning, or promotes
> discrimination. **If an Item contains an image of a person, even if the Item has
> a model release, you can't use it in a way that creates a fake identity, implies
> personal endorsement of a product by the person, or in connection with sensitive
> subjects.**"

Envato's sensitive-subject bar is **scoped to items containing a person**. Footage
with no identifiable human in frame is outside it. That scoping is what makes
Envato usable here and Storyblocks not.

**Pexels**:
> "Identifiable people may not appear in a bad light or in a way that is
> offensive."

**Pixabay**:
> "You cannot use Content in any immoral or illegal way, especially Content which
> features a recognisable person."
>
> And the warranty disclaimer that matters: "We do not warrant that any consents
> or licenses have been obtained in relation to any Content, and we expressly
> disclaim any and all responsibility and liability in relation to such matters."

**Magnific (ex-Videvo/Freepik)** — prohibits use that
> "places any person appearing in the Magnific Content in a negative light"

**Adobe Stock** — **NOT VERIFIED.** `stock.adobe.com/license-terms` renders the
licence *comparison* only; the words "sensitive", "unflattering", "model" and
"defamatory" do not appear on it. The binding document is the PDF at
`adobe.com/cc-shared/assets/pdf/legal/servicetou/stock-product-specific-terms-en-us-20260116.pdf`,
which failed to download (connection reset) and timed out in WebFetch on
2026-08-12. **GUESS**, flagged as such: Adobe's terms almost certainly mirror
Getty's disclaimer model, but I did not read them and it should not be relied on.

### 2.4 Attribution, monetization, and survival — stock

| Service | Attribution required? | Monetized YouTube OK? | Survives lapse? |
|---|---|---|---|
| Pexels | "Attribution is not required." | yes (no restriction found) | n/a — free, irrevocable in practice |
| Pixabay | not required, "appreciated" | yes | "irrevocable, worldwide, perpetual ... non-exclusive and royalty-free right" |
| Mixkit | "Attribution is not required, however, we would appreciate it if you credit Mixkit where reasonably possible." | yes | **Revocable** — Envato "can terminate your rights under the Mixkit License" |
| Magnific | **required on the free tier**; removed by Premium/Pro | yes | not established — **NOT VERIFIED** |
| Storyblocks | none required | yes | **yes** — see below |
| Envato Elements | none required | yes | **yes, once the End Product is completed** — see below |
| Artlist | none required | yes (clearlist) | **yes** — §2, quoted in §1.3 |
| Adobe Stock | none | yes | "An Adobe Stock perpetual, worldwide license allows you to use your licensed asset in all media" |

**Storyblocks** §1.2 does grant perpetuity, and §5 only stops *new* downloads:
> "1.2 Each license under an applicable subscription plan grants the user a
> worldwide, non-exclusive, non-sub-licensable, non-transferable and **perpetual**
> royalty-free license to reproduce, distribute, publish, transmit and display..."
>
> "5. ... If your subscription expires you shall have no further right or
> authorization to download and use any **additional** Stock Files from the
> Platform."

**Envato Elements** — perpetual, but conditional on *finishing* the video first:
> "License commencement: The license for an Item starts when you download the Item
> or create a new license for an Item and the license is only valid if you
> complete the End Product while your subscription is active. **Once the Item has
> been incorporated into a completed End Product during an active subscription
> term, the license becomes perpetual, which means that it continues for the life
> of the End Product, even after your subscription ends.**
>
> If you cancel your subscription and have not completed your End Product, the
> license for the Item is terminated and you have no further rights to use the
> Item."

⚠️ **Envato's operational trap for a daily channel:** the licence is *per project*.
> "If you want to use the same Item for separate projects, you will need to create
> a new license for each end-use."

Reusing one favourite courthouse-exterior clip across 30 videos requires **30
separate licence registrations**. Miss them and every video after the first is
unlicensed. This has to be a step in the publish checklist, not a good intention.

Also: **"You can't use music items in a Broadcast presentation."** Envato's *music*
is not a substitute for a music subscription if broadcast is ever in scope.

---

## 3. THE SPECIFIC LEGAL QUESTION — generic stock next to a named defendant

### 3.1 The framing in the brief is wrong for Texas, and that matters

The brief asks about **false light**. **Texas abolished that tort.**

Digital Media Law Project, dmlp.org/legal-guide/texas-false-light:
> "The tort of 'false light' is not recognized in Texas; you cannot sue or be sued
> on such a claim. See *Cain v. Hearst Corp.*, 878 S.W.2d 577, 579-80 (Tex. 1994)."

Citation confirmed independently via CourtListener's API:
*Cain v. Hearst Corp.*, 878 S.W.2d 577, Supreme Court of Texas, decided
1994-06-22.

This is not merely a technicality — it removes the "emotional distress from a
false implication" theory entirely. It does **not** make us safe. It moves the
exposure to a tort Texas very much does recognise.

### 3.2 The tort that does apply: defamation by implication

*Turner v. KTRK Television, Inc.*, 38 S.W.3d 103, 115 (Tex. 2000), quoted verbatim
in *Dallas Morning News, Inc. v. Tatum*, 554 S.W.3d 614, 627 (Tex. 2018)
(fetched from CourtListener opinion 4498964 on 2026-08-12):

> "that a plaintiff can bring a claim for defamation when discrete facts,
> literally or substantially true, are published in such a way that they create a
> substantially false and defamatory impression by **omitting material facts or
> juxtaposing facts in a misleading way**."

And on the standard:
> "a defendant may be liable for a 'publication that gets the details right but
> fails to put them in the proper context and thereby gets the story's *gist*
> wrong.'"

> "[i]n making the initial determination of whether a publication is capable of a
> defamatory meaning, we examine its 'gist.' That is, we construe the publication
> 'as a whole ....'"

**Read that against our format.** Every safety rule in `SAFETY_RULES.md` is about
the *audio* being true. Defamation by implication does not care. A clip in which
every spoken word is accurate can still be actionable if the assembled whole —
audio plus B-roll plus title plus thumbnail — conveys a false gist. "Juxtaposing
facts in a misleading way" is a precise description of cutting stock handcuffs
against a named defendant who was never handcuffed.

*Tatum* also shows Texas courts treating **visual juxtaposition as part of the
gist**. Describing *Rosenthal*, the court noted the article was
> "published under the heading \"CRIME\" and [was] accompanied by Rosenthal's mug
> shot from a prior unrelated charge."

The mug shot was part of what made the piece capable of defamatory meaning. A
stock shot standing in for an event that did not happen is the same mechanism.

### 3.3 What practitioners actually do

**The licence-level answer (Getty / Artlist):** a visible on-screen disclaimer
naming the footage as stock and the people as models — *"Stock footage. Posed by
model."* Getty spells out both required elements: (1) illustrative purposes only,
(2) any person depicted is a model. This is contractual, not merely ethical: on
Getty's and Artlist's terms it is what makes the use licensed at all.

**The newsroom answer:** the DMLP guidance is directly on point and describes our
exact risk twice —
> "For instance, an article about sex offenders illustrated with a stock
> photograph of an individual who is not, in fact, a sex offender could give rise
> to a false light claim, even if the article and photo caption never make the
> explicit false statement (i.e., identifying the person in the photo as a sex
> offender) that would support a defamation claim."

> "False light lawsuits often arise on the margins of stories, rather then at
> their core. For example, one might use a stock photo of a particular street to
> illustrate a story on local prostitution, and inadvertently create the
> impression that a person caught at random in the photo was frequenting the
> prostitutes. **Be careful in what you use to illustrate your work.**"

> "Be sure that your website doesn't get reformatted in such a way as to create an
> **unwitting juxtaposition of images and stories** that creates a connotation
> that you had not intended."

**RTDNA Code of Ethics** (rtdna.org/ethics) is more sceptical of labelling than
the licence writers are:
> "Staging, dramatization and other alterations – even when labeled as such – can
> confuse or fool viewers, listeners and readers. These tactics are justified only
> when stories of great significance cannot be adequately told without distortion,
> and when any creative liberties taken are clearly explained."

Note the tension, and resolve it in RTDNA's favour: **a label makes the use
licensed; it does not make it honest.** The licence disclaimer protects us from
the stock vendor. It does not reliably protect us from the defendant.

BBC Editorial Guidelines and AP News Values could not be retrieved
(`bbc.com` and `ap.org` blocked to this tool on 2026-08-12) — **NOT VERIFIED**,
and they would only corroborate, not change, the above.

### 3.4 Operating rule this produces

Ranked by how much protection each buys:

1. **Prefer no stock at all next to a named person.** Use the court's own frame,
   held or slowed, or a black card with type. Nothing beats footage of the actual
   proceeding for a channel whose whole asset is footage of the actual proceeding.
2. **If stock is used, use footage with no identifiable human in frame.** This
   single rule takes us outside Envato's sensitive-subject bar, outside Pexels'
   and Pixabay's "recognisable person" bars, outside Magnific's "negative light"
   bar, and removes the *Turner* "is that him?" reading in one move.
3. **Never cut stock depicting an act (handcuffing, an arrest, a cell door, a
   struggle) against a named defendant.** That is the literal
   "juxtaposing facts in a misleading way" case.
4. **Persistent corner super — `STOCK FOOTAGE — NOT OF THIS CASE`** — on every
   frame of non-courtroom footage, not a title card at the head. Getty and Artlist
   both require the disclaimer to accompany *the use*.
5. **Storyblocks §2.2/§2.5 cannot be cured by a disclaimer.** If Storyblocks is
   chosen anyway, the breach is structural, not fixable with a super.

This belongs in `SAFETY_RULES.md` as a new rule — the existing R1–R7 constrain
words and cuts, and none of them reach the picture.

---

## 4. THE COURTROOM FOOTAGE ITSELF

### 4.0 Headline: `SAFETY_RULES.md` overstates the position

`SAFETY_RULES.md` opens with:
> "Texas district court proceedings are public record and the court publishes
> this livestream itself. Clipping it is lawful."

**No fetched source supports the third sentence, and two cut against it.** The
first two sentences are correct and now cited below. The third is an inference
presented as a finding. It should be rewritten.

Nothing found *prohibits* reuse either. The honest statement of the position is:
**no instrument addresses downstream reuse at all, in either direction** — every
Texas rule located regulates *capture at the source*, not use of an
already-published stream. But two facts make "lawful" the wrong word:

1. **The videos are under the Standard YouTube License, not Creative Commons.**
   Watch pages for `4f2BPGijYkI`, `LzL4WchP-pI` and `I-xclg5NhAA` contain no
   "Creative Commons" string and no License metadata row. The channel's About
   panel carries **no** terms, attribution request, or reuse grant — the
   `channelMetadataRenderer` shows `"description":""`. Our counterparty risk here
   is not the court; it is **YouTube's own Terms of Service**, which prohibit
   downloading content absent a download button or written permission. That is
   the mechanism most likely to bite a monetized channel, and it is entirely
   separate from Texas law.

2. **OCA's own published guidance tells judges to forbid exactly this**, and
   names the sanction. txcourts.gov/programs-services/electronic-hearings-zoom/,
   answering *"Can't people record the YouTube live stream with their phone?"*:
   > "Just as in a physical courtroom, participants may record proceedings against
   > the direction of the court. **Judges should admonish participants and viewers
   > that recording is not permitted and can be enforced with contempt.**"

   OCA further distributes a **"DO NOT RECORD" watermark** for judges to overlay
   on these streams (`txcourts.gov/media/1446546/do-not-record.png`).
   **GUESS, explicitly flagged:** Judge Boyd's channel does not appear to use it —
   no `DO NOT RECORD` string in the served watch-page HTML — but YouTube can
   deliver branding watermarks outside that payload, so this is *not* a
   measurement and must not be relied on. **Someone should watch a stream and look
   at the corner of the frame.** If that watermark is present, the position
   changes materially.

### 4.1 The stream is official — this part is solid

The Office of Court Administration's statewide directory lists it. Endpoint
`streams.txcourts.gov/LiveStream/GetAllChannels` returns the row:
> `["Boyd", "187th District Court", "Bexar County", "<a href=\"http://www.youtube.com/channel/UCiBt-ijBAoKLiWNwOYogbAQ\"> Watch </a>"]`

Channel: `youtube.com/@judgestephanieboyd4233` (ID `UCiBt-ijBAoKLiWNwOYogbAQ`),
"Judge Stephanie Boyd", joined 2020-04-21, 59K subscribers, 1,752 videos,
9,268,469 views. Video descriptions are bare, e.g.
`"Monday, December 15, 2025 / Judge Stephanie Boyd / 187th District Court /
Bexar County, Texas / Morning Docket"`.

Constitutional grounding, from the same OCA page:
> "The Open Courts Provision of the Texas Constitution requires that all courts
> maintain public access."
>
> *Does streaming hearings to YouTube satisfy the open court provisions?* — "Yes,
> as long as the court provides notice of the streaming and makes the proceeding
> public."

Note also, from OCA:
> "There is no requirement to keep the proceeding on YouTube after the completion
> of the hearing. **It may be deleted immediately.**"

Operational consequence: **the source can vanish.** Our own archive of the
material we have clipped is the only durable copy. R7's takedown ledger assumes
we can always re-derive from source; we cannot.

### 4.2 Bexar County's own rule — capture only

Bexar County Criminal District Court Local Rules, Special Order No. 73522, signed
2025-06-10 by all ten criminal district judges **including Stephanie Boyd**,
posted to OCA TOPICs 2025-06-30
(`topics.txcourts.gov/LocalRulesPublic/PreviewAttachment/2438`):

> **1.5 Courtroom Media**
> **1.5.1** The taking of photographs, the televising, or broadcasting by news
> media outlets of judicial proceedings in the courtroom that disturbs the order
> or decorum of the courtroom while in session or in recess is prohibited.
> **1.5.2** Non-disruptive photographing, televising, or broadcasting by news
> media outlets in the courtroom shall be allowed at the discretion of the court.
> **1.5.3** Photographing, televising, or broadcasting by the general public is
> not permitted.

Rule 1.5 is the **only** media provision in the 9-page rules. There is nothing
about the court's own livestream, its archive, or downstream reuse. 1.5.3 governs
being in the room, not re-publishing what the court itself broadcast.

Contrast the civil side (`bexar.org/DocumentCenter/View/23495`), Local Rule 1:
> "Proceedings shall not be recorded in any format unless specific permission to
> record is granted by the court. See Texas Rule of Civil Procedure 18c."

### 4.3 TRCP 18c — verbatim, and why it is only half-relevant

From `txcourts.gov/media/1462349/texas-rules-of-civil-procedure.pdf` (last amended
2026-07-01), printed p.14:

> **RULE 18c. RECORDING AND BROADCASTING OF COURT PROCEEDINGS**
> A trial court may permit broadcasting, televising, recording, or photographing
> of proceedings in the courtroom only in the following circumstances:
> (a) in accordance with guidelines promulgated by the Supreme Court for civil
> cases, or
> (b) when broadcasting, televising, recording, or photographing will not unduly
> distract participants or impair the dignity of the proceedings and the parties
> have consented, and consent to being depicted or recorded is obtained from each
> witness whose testimony will be broadcast, televised, or photographed, or
> (c) the broadcasting, televising, recording, or photographing of investiture, or
> ceremonial proceedings.

Two caveats: 18c is a **civil** rule and the 187th is a **criminal** court; and
**NOT FOUND** — the "guidelines promulgated by the Supreme Court" that 18c(a)
refers to are not on `txcourts.gov/rules-forms/rules-standards/` and not in the
TRCP PDF.

The current standing open-courts rule, TRCP 21d(f) (added 2023), mandates
*observation* and is silent on recording or reuse:
> "**(f) Open Courts.** If a court conducts a court proceeding in which all
> participants appear electronically, the court must: (1) provide reasonable
> notice to the public of how to observe the court proceeding; and (2) provide the
> public the opportunity to observe the court proceeding, unless the court has
> determined that it must close the court proceeding to protect an overriding
> interest..."

The COVID emergency orders are a dead end: the Twenty-Second (Misc. Docket
20-9095) was read in full and the Twelfth, Seventeenth and Twenty-Eighth
text-scanned — **none contains "broadcast", "YouTube" or "livestream"**. The
YouTube mandate lives in OCA guidance, not in any order.

### 4.4 New statute — Gov't Code § 21.014, effective 2025-09-01

Added by Acts 2025, 89th Leg., R.S., Ch. 11 (S.B. 836), Sec. 8:

> **Sec. 21.014. ELECTRONIC TRANSMISSION OF COURT PROCEEDINGS IN CERTAIN CASES
> PROHIBITED.** ... (b) A court may not allow the electronic transmission or
> broadcasting of court proceedings described by Subsection (a) in which evidence
> or testimony is offered that depicts or describes acts of a sexual nature unless
> the court provides notice to and receives express consent for the transmission
> or broadcasting from: (1) the victim or the parent, conservator, or guardian of
> the victim, as applicable; (2) the attorney representing the state; and (3) the
> defendant.

Subsection (a) covers Penal Code 21.02 (continuous sexual abuse of a child), 21.11
(indecency with a child), 21.15 (invasive visual recording), 22.011 (sexual
assault), 22.012 (indecent assault), 22.021 (aggravated sexual assault), Chapter
20A trafficking offences, and protective-order proceedings.

This binds **the court**, not us. But it defines a category of stream content that
should not exist, and if it appears anyway it is the highest-risk material on the
channel. **This directly undercuts the premise of `SAFETY_RULES.md` that "the
court redacts at the source" and "if it aired on the public stream, it is
usable."** § 21.014 is thirteen months old; a court can get it wrong, and the
statute's existence is proof the Legislature thought courts were getting it wrong.
Sex-offence and protective-order dockets should be an explicit exclusion in our
own pipeline rather than something we delegate to the court's judgement.

### 4.5 Rule 12 and the Public Information Act — neither helps

**TRJA Rule 12 does not reach these recordings.** Rule 12.2(d)
(`txcourts.gov/media/1462987/texas-rules-of-judicial-administration-07012026.pdf`):
> "**Judicial record** means a record made or maintained by or for a court or
> judicial agency in its regular course of business **but not pertaining to its
> adjudicative function** ... **A record of any nature created, produced, or filed
> in connection with any matter that is or has been before a court is not a
> judicial record.**"

A docket recording is created in connection with matters before the court →
not a judicial record → Rule 12 does not apply. The TRJA PDF contains **zero**
instances of "broadcast", "stream", "livestream", "YouTube" or "remote
proceeding".

**The PIA excludes the judiciary outright.** Gov't Code § 552.003(1)(B)(i):
"governmental body"… "does not include: (i) the judiciary". And § 552.0035(a):
> "Access to information collected, assembled, or maintained by or for the
> judiciary is governed by rules adopted by the Supreme Court of Texas or by other
> applicable laws and rules."

So the PIA grants us no right of access and imposes no duty on the court. Access
rests on the constitutional open-courts line plus the court's voluntary
publication — and voluntary publication can stop (§4.1).

### 4.6 Copyright — nobody has claimed it, and nothing strips it

- **17 U.S.C. § 105(a)** puts *federal* works in the public domain: "Copyright
  protection under this title is not available for any work of the United States
  Government..." **It does not reach Texas or Bexar County.** The common creator
  belief that "government footage is public domain" is a federal rule being
  misapplied to a state court.
- **NOT FOUND: any Texas statute placing state or county works in the public
  domain.** All 45 Texas statute sections containing "copyright" were enumerated.
  The corpus runs the *opposite* way — **Local Gov't Code § 270.009 "Intellectual
  Property of County"** expressly lets a county obtain "a copyright of an original
  work of authorship fixed in any tangible medium of expression".
- **NOT FOUND: any copyright, reuse or terms-of-use statement anywhere in the
  chain** — not on the channel About, not in video descriptions, not on
  `bexar.org/1787/187th-Criminal-District-Court` (106,787 bytes of HTML, no
  livestream link, no YouTube link, no media policy), not on `bexar.org/privacy`,
  not on `txcourts.gov/site-policies/`.

**GUESS, labelled as such:** nobody has asserted rights and no statute strips
them, so the copyright position is *unresolved*, not *clear*. Three candidate
owners exist and none has spoken: OCA says a channel may be owned by the court
*or* by the individual judge, and § 270.009 separately empowers the county.

### 4.7 Others are already doing it

YouTube surfaces "Vikky's Court Watch" ("Judge Boyd's Criminal Docket From August
10th, 2026", 1 day old) and "Scales Of Justice" ("Mon, May 04, 2026 | Judge
Stephanie Boyd | 187th District Court | Highlights"). Recorded as an observation
only. **Other channels not having been sued yet is not a licence**, and it is
exactly the reasoning that produces a six-month-out surprise.

### 4.8 What this changes

1. Rewrite the `SAFETY_RULES.md` preamble. Replace "Clipping it is lawful" with
   the accurate version: *the proceedings are public, the court publishes the
   stream voluntarily, no Texas rule addresses reuse of an already-published
   stream in either direction, and the videos carry the Standard YouTube License.*
2. Add sex-offence and protective-order dockets (Gov't Code § 21.014(a)) as a
   hard exclusion, rather than relying on the court to have excluded them.
3. Check a live stream for the OCA "DO NOT RECORD" watermark. This is a
   five-minute task with a material bearing on the position.
4. Archive locally. The court may delete at will.
5. The realistic first-mover against us is **YouTube's ToS on downloading**, not
   Bexar County. Worth a considered answer before scaling output.

---

## 5. RECOMMENDATION

### Music — **Uppbeat Essentials, $83.88/yr** (COMPUTED from `$6.99/month`, yearly billing)

Chosen over Epidemic Sound (which has the larger catalogue and costs only $36/yr
more) for one reason: **Uppbeat's survival guarantee is in the contract and
Epidemic's is in an FAQ.** Uppbeat clause 6.4 covers the content and clause 11.3.5
separately covers the *safelist*, so videos published during the term stay
claim-protected after cancellation. Epidemic's equivalent promise appears only on
a marketing page; their subscription-terms URL 404'd on 2026-08-12 and I could not
read the binding document.

Essentials includes `Safelist 1 YouTube channel` — sufficient for one channel.
Register Texas Trial Tracker's channel ID on the safelist **before** the first
upload, not after.

> **Single biggest risk:** clause 4.1.2 — content must not be
> *"defamatory, discriminatory, obscene, promoting hatred, violence or cruelty ...
> or intimidating or humiliating any person."* A channel built on naming criminal
> defendants sits closer to "humiliating any person" than any other Uppbeat
> customer, Uppbeat interprets that clause, and clause 16.1 lets them terminate on
> unremedied material breach. Compounding it, clause 3.7 disclaims any guarantee
> that Content ID claims won't happen anyway. **Mitigation:** the free tier is $0
> and identical in mechanism — run one video through it and confirm no claim
> lands before paying for a year.

*Cheaper fallback if any spend needs justifying first:* the **YouTube Audio
Library, $0**, is the only source in this document where YouTube itself
guarantees no Content ID claim, with no whitelist to file and no lapse risk. Its
catalogue is dull, which is a craft problem, not a rights problem.

### Stock — **Envato Elements Core, $198/yr**, under a no-people rule

`$16.50/month billed annually`, elements.envato.com/pricing.

The decisive comparison is not price. Storyblocks at $252/yr **prohibits the use
outright** — §2.5 has no people-limitation and no disclaimer cure, and §2.2
expressly reaches "juxtaposition with other material or subject matter". Envato's
sensitive-subject bar is scoped to *"an Item [that] contains an image of a
person"*, so a self-imposed rule of **no identifiable humans in any stock clip**
puts us cleanly inside the licence — and, per §3.4, simultaneously removes most of
the *Turner* defamation-by-implication exposure. One rule solves the contract
problem and the tort problem together. Envato's perpetuity clause is also explicit
and survives cancellation once the video is finished.

> **Single biggest risk: the per-project licence.** *"If you want to use the same
> Item for separate projects, you will need to create a new license for each
> end-use."* A daily channel reusing a stock courthouse exterior across 30 videos
> needs 30 registrations; forgetting means every video after the first is
> unlicensed, and the perpetuity clause never attaches to them. **Mitigation:**
> make licence registration a hard gate in the publish pipeline, logged in the
> clip manifest next to the source timestamps, so it fails loudly like R7 does.

*If the no-people rule proves too limiting* — if the edit genuinely needs people
in stock shots — the only library found that **permits** it is **Artlist Max at
$607.92/yr**, via the §5 *"Stock footage, posed by model"* cure, and that price
also absorbs the music subscription (making Uppbeat redundant, so the true delta
is ~$524/yr). That is the correct upgrade path, and the only one. It is not the
default because a courtroom channel should not need stock humans at all.

---

## Appendix — what could not be verified on 2026-08-12

| Item | Why | URL attempted |
|---|---|---|
| Epidemic Sound binding subscription terms | HTTP 404 | epidemicsound.com/terms/subscription-terms/ |
| Adobe Stock sensitive-use clause | PDF download connection reset; WebFetch timeout | adobe.com/cc-shared/assets/pdf/legal/servicetou/stock-product-specific-terms-en-us-20260116.pdf |
| Soundstripe Pro/Pro Plus/Business prices | not rendered on public page | soundstripe.com/library/pricing |
| Artgrid standalone pricing | folded into Artlist Max; no separate page reachable | — |
| Magnific subscription prices | not retrieved | magnific.com |
| BBC Editorial Guidelines | host blocked to this tool | bbc.com/editorialguidelines |
| AP News Values (visuals) | host blocked to this tool | ap.org |
| Ofcom Broadcasting Code §7 | HTTP 403 | ofcom.org.uk |
| *Cain v. Hearst* full opinion text | Justia 403, casetext blocked; citation confirmed via CourtListener API + DMLP | — |

### Section 4 — searched for and genuinely absent

These are **NOT FOUND** after direct inspection, not "not looked for":

| Item | Where I looked |
|---|---|
| Any Bexar County / 187th statement on reuse, rebroadcast or clipping of the livestream | bexar.org `/1787`, `/1902`, `/1703`, `/courts`, `/privacy`; TOPICs court ID 313 (all 11 attachments); Bexar criminal local rules in full; Bexar civil local rules |
| Supreme Court broadcasting guidelines referenced by TRCP 18c(a) | txcourts.gov/rules-forms/rules-standards/; the TRCP PDF itself |
| Any Texas rule or statute on what the public may do with an already-published court stream | TRCP, TRJA, Gov't Code, Local Gov't Code, all COVID emergency orders checked |
| Any Texas statute placing state/county works in the public domain | all 45 Texas statute sections containing "copyright" enumerated |
| Any copyright or terms-of-use assertion by the court, county, judge or OCA | channel About (empty), video descriptions, bexar.org, txcourts.gov/site-policies/ |
| Whether the OCA "DO NOT RECORD" watermark is burned into Boyd's stream | inferred absent from watch-page HTML — **this is a GUESS, not a measurement.** Resolve by eye. |
