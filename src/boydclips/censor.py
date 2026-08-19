"""Censor profanity in TEXT only. Audio is never touched.

Channel rule (Nathan, 2026-08-13): "leave the sound in but always cencor it in
the text pls." Testimony audio ships uncensored -- the courtroom record is the
product. Every rendered text surface is censored, because text is what gets
indexed, thumbnailed and read stripped of the footage around it.

Style: first letter kept, middle asterisked, trailing letters kept -> f***ing.
The reader must still know exactly which word was said. Never delete, never
paraphrase.

This lives in the package rather than in scripts/ so the renderer and the
packaging stage can import it. `scripts/censor.py` re-exports it and keeps the
documented CLI path (`python scripts/censor.py in.srt out.srt`) working.
"""

from __future__ import annotations

import re

# Stems, not inflections -- the pattern handles suffixes.
_STEMS = [
    "fuck", "shit", "bitch", "cunt", "cock", "dick", "pussy", "asshole",
    "bastard", "motherfuck", "goddamn", "nigger", "nigga", "faggot", "whore",
    "twat", "wank", "prick", "slut",
]

# A stem can sit inside a longer word: "bullshit", "dipshit", "dumbass" all
# carry it. A leading \b alone missed every one of those, so the prefix is
# captured and preserved -> "bulls***", which still tells the reader the word.
_PATTERN = re.compile(
    r"\b([a-z]*?)(" + "|".join(sorted(_STEMS, key=len, reverse=True)) + r")([a-z]*)\b",
    re.IGNORECASE,
)

# The cost of the prefix/suffix latitude above is false positives, and on a DWI
# docket "cocktail" is a word that actually gets said. Anything here is exempt
# regardless of what the pattern thinks it found.
_INNOCENT = frozenset(
    {
        "cocktail", "cocktails", "cockpit", "cockroach", "cockroaches", "cocky",
        "cockle", "cockles", "peacock", "peacocks", "shuttlecock",
        "dickens", "dickinson", "dickey", "dickerson",
        "prickly", "prickle", "prickles", "prickling",
        "titmouse", "scunthorpe",
    }
)


def _mask(m: re.Match) -> str:
    prefix, stem, suffix = m.group(1), m.group(2), m.group(3)
    if (prefix + stem + suffix).lower() in _INNOCENT:
        return m.group(0)
    # keep any leading cluster, keep the stem's first char, star the rest of the
    # stem, keep the suffix
    return prefix + stem[0] + "*" * (len(stem) - 1) + suffix


def censor(text: str) -> str:
    """Censor profanity in a string of display text."""
    return _PATTERN.sub(_mask, text)


def has_profanity(text: str) -> bool:
    """True only if censoring would actually change the text.

    Asking the pattern directly reports a hit on the _INNOCENT words too, which
    made "we had a cocktail" test positive.
    """
    return censor(text) != text
