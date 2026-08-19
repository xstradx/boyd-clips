"""Is this a contested evidentiary hearing? If so it is unusable, whatever it scores.

NATHAN'S RULE, 2026-08-18: "we can't even use that video it's a bench trial."

WHY IT IS STRUCTURAL, NOT A JUDGEMENT CALL
------------------------------------------
When witnesses testify, the 187th's courtroom camera pulls back to cover the
witness box, counsel tables and the gallery. The defendant stops being a person
at a podium and becomes a small figure in a wide room shot. Verified by pulling
frames:

  Miosek  cj9gKdNcJdk:5277  contested revocation, witnesses  -> wide room shot,
          nobody at the podium, faces a few percent of frame height
  Pena    oL6lV6gCyOc:3047  contested PSI sentencing         -> camera off, a
          black "187TH DC" name card for all 51 minutes
  Blackburn 4zkUTUavW4I:116 sentencing w/ family testimony   -> 3-4 tile grid,
          short was unpostable, every tile ~1/4 width

Against the two clips that were actually approved:

  Thompson  JgvW7oCQxuI:6698  plea/sentencing at the podium -> tight 2-up,
            defendant in orange and counsel legible on the left, Boyd on the right
  Rodriguez mvGmUbuS0sU:1358  same shape                     -> same

So the transcript-reading rubric and the pixel-reading camera probe were both
measuring downstream of one upstream fact: WHO IS THE CAMERA POINTED AT, which
is decided by whether the hearing takes evidence.

Cheap to detect, and it needs no video at all. A contested evidentiary hearing
leaves unmistakable marks in the transcript: witnesses are sworn, counsel passes
the witness, exhibits are offered and admitted, objections are ruled on. A plea
or a docket sentencing has almost none of them.

RUNS BEFORE THE DOWNLOAD, AFTER THE SAFETY GATE. It decides whether a clip is
shootable, never whether it is publishable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Weighted because they are not equally diagnostic. Swearing a witness and
# passing the witness happen in nothing else; "objection" leaks into ordinary
# argument, so it counts for less.
MARKERS: dict[str, tuple[str, float]] = {
    "swear_in":    (r"\b(do you (solemnly )?swear|raise your right hand|under (oath|penalty))\b", 3.0),
    "pass_witness":(r"\b(pass the witness|no further questions|your witness|may this witness be excused)\b", 3.0),
    "examination": (r"\b(direct examination|cross[- ]examination|redirect|voir dire the witness)\b", 3.0),
    "take_stand":  (r"\b(take the stand|takes the stand|calls? .{0,30}to the stand|state calls|defense calls)\b", 2.5),
    "exhibit":     (r"\b(exhibit (number |no\.? )?\w+|offer .{0,20}into evidence|admitted into evidence|publish(ed)? to)\b", 2.0),
    "objection":   (r"\b(objection|sustained|overruled|move to strike|asked and answered|speculation)\b", 1.0),
    "approach":    (r"\b(approach the bench|may I approach|sidebar)\b", 1.5),
    "testimony":   (r"\b(testif(y|ied|ies|ying)|the witness|his testimony|her testimony)\b", 1.0),
}

# CALIBRATED on eight cases with known visual outcomes. ABSOLUTE COUNTS of the
# three discriminating markers — not a rate.
#
# FIRST ATTEMPT, RECORDED SO IT IS NOT RETRIED: weighted marks per MINUTE,
# threshold 1.0. Scored 5/8 and failed in both directions. Thompson — an
# approved, perfectly shootable 4-minute plea — was flagged CONTESTED because
# two "do you swear" hits inside a short span produce a high rate. Blackburn
# (33.8 min) and Pena (51.1 min) were passed as clean because their real
# evidentiary marks were diluted across a long hearing. Normalising by length
# is exactly wrong here: taking evidence is a fact about the hearing, not a
# density.
#
# "Do you swear" is also NOISE and is excluded from the decision — the plea
# colloquy swears in the defendant. Thompson and Rodriguez both hit it twice.
#
# Counts on the calibration set (bold = what fires):
#   Thompson   pass_witness 0  objection  1  exhibit  0   -> clean
#   Rodriguez  pass_witness 0  objection  0  exhibit  0   -> clean
#   McCaskill  pass_witness 0  objection  0  exhibit  0   -> clean
#   Kilpatrick pass_witness 0  objection  0  exhibit  0   -> clean
#   Miosek     pass_witness 4  objection 43  exhibit  7   -> CONTESTED
#   Measeck    pass_witness 5  objection 22  exhibit 16   -> CONTESTED
#   Blackburn  pass_witness 1  objection  0  exhibit  0   -> CONTESTED
#   Pena       pass_witness 0  objection 13  exhibit  2   -> CONTESTED
#
# One pass-the-witness is enough on its own: it cannot happen without a witness
# on the stand, and the moment there is one the camera goes wide.
PASS_WITNESS_MIN = 1
OBJECTION_MIN = 5
EXHIBIT_MIN = 3


@dataclass
class Verdict:
    contested: bool
    minutes: float
    hits: dict[str, int] = field(default_factory=dict)
    fired: list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        if not self.contested:
            return "not an evidentiary hearing"
        return "bench trial / contested evidentiary hearing — " + ", ".join(self.fired)


def classify(text: str, minutes: float) -> Verdict:
    """Score a case's own transcript span. `text` is that span only.

    Returns contested=True when the hearing takes evidence, which on this
    docket means the camera pulls back to a wide room shot and the case is
    unshootable regardless of how well it scores on the rubric.
    """
    low = (text or "").lower()
    hits = {name: len(re.findall(pat, low)) for name, (pat, _) in MARKERS.items()}
    fired = []
    if hits.get("pass_witness", 0) >= PASS_WITNESS_MIN:
        fired.append(f"witness passed x{hits['pass_witness']}")
    if hits.get("objection", 0) >= OBJECTION_MIN:
        fired.append(f"objections x{hits['objection']}")
    if hits.get("exhibit", 0) >= EXHIBIT_MIN:
        fired.append(f"exhibits x{hits['exhibit']}")
    if hits.get("examination", 0) >= 1:
        fired.append(f"direct/cross x{hits['examination']}")
    if hits.get("take_stand", 0) >= 2:
        fired.append(f"called to stand x{hits['take_stand']}")
    return Verdict(bool(fired), round(max(0.5, minutes), 1), hits, fired)
