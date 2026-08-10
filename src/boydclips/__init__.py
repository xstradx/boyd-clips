"""Boyd Clips — automated clipping of a public court livestream.

Stages are separable and each is independently testable:

    discover    find new docket streams          (metadata only)
    transcribe  word-timed transcript            (captions, no video)
    analyze     segment, safety-gate, score      (Claude)
    render      download section, cut, caption   (yt-dlp + ffmpeg)
    publish     long-form first, then the short  (platform APIs)

Policy lives in config/ and spec/. Code should never encode a threshold,
format rule, or safety rule that a human might reasonably want to change.
"""

__version__ = "1.0.0"
