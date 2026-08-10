"""Stage 4 — publication.

The funnel constrains the order: the long-form must publish first so its URL
exists before the short's description is written. `publish_pair` enforces that;
nothing else should call the platform adapters directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .config import Config
from .state import Store

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_PATH = Path(__file__).resolve().parents[2] / "config" / "youtube_token.json"
CLIENT_SECRET_PATH = Path(__file__).resolve().parents[2] / "config" / "youtube_client_secret.json"


@dataclass
class PublishResult:
    platform: str
    remote_id: str
    url: str
    privacy: str


class Publisher(Protocol):
    name: str

    def publish(
        self, video: Path, title: str, description: str, privacy: str, **kw: Any
    ) -> PublishResult: ...


# ---------------------------------------------------------------------- YouTube


class YouTubePublisher:
    name = "youtube"

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def _service(self) -> Any:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "YouTube publishing needs the Google client libraries:\n"
                "  pip install google-api-python-client google-auth-oauthlib"
            ) from exc

        creds = None
        if TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), YOUTUBE_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not CLIENT_SECRET_PATH.exists():
                    raise RuntimeError(
                        f"Missing {CLIENT_SECRET_PATH.name}.\n"
                        "Create an OAuth desktop client in Google Cloud Console with the\n"
                        "YouTube Data API v3 enabled, download the JSON, and save it there.\n"
                        "Then run: boyd auth youtube"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CLIENT_SECRET_PATH), YOUTUBE_SCOPES
                )
                creds = flow.run_local_server(port=0)
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

        return build("youtube", "v3", credentials=creds, cache_discovery=False)

    def authorize(self) -> None:
        self._service()

    def publish(
        self, video: Path, title: str, description: str, privacy: str, **kw: Any
    ) -> PublishResult:
        from googleapiclient.http import MediaFileUpload

        service = self._service()
        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": kw.get("tags") or self.cfg.get("packaging.longform.tags", []),
                "categoryId": str(self.cfg.get("publish.youtube.category_id", "25")),
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": bool(
                    self.cfg.get("publish.youtube.made_for_kids", False)
                ),
            },
        }

        media = MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True)
        request = service.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            _, response = request.next_chunk()

        vid = response["id"]
        return PublishResult(
            platform=self.name,
            remote_id=vid,
            url=f"https://www.youtube.com/watch?v={vid}",
            privacy=privacy,
        )


# ------------------------------------------------------------- TikTok / IG stubs


class TikTokPublisher:
    name = "tiktok"

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def publish(self, video: Path, title: str, description: str, privacy: str, **kw: Any):
        token = os.environ.get("TIKTOK_ACCESS_TOKEN")
        if not token:
            raise RuntimeError(
                "TikTok publishing is not configured.\n"
                "It needs a TikTok for Developers app with the Content Posting API\n"
                "scope approved (review takes days to weeks). Until the app is\n"
                "audited, the API can only post to SELF_ONLY/draft.\n"
                "Set TIKTOK_ACCESS_TOKEN in config/.env once approved, then\n"
                "implement the FILE_UPLOAD init/upload/publish sequence here."
            )
        raise NotImplementedError(
            "TikTok Content Posting API call not implemented — add it once the "
            "app audit clears and the exact scopes granted are known."
        )


class InstagramPublisher:
    name = "instagram"

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def publish(self, video: Path, title: str, description: str, privacy: str, **kw: Any):
        token = os.environ.get("IG_ACCESS_TOKEN")
        user_id = os.environ.get("IG_USER_ID")
        if not (token and user_id):
            raise RuntimeError(
                "Instagram publishing is not configured.\n"
                "Reels require a Business/Creator account linked to a Facebook Page\n"
                "and a Meta app with instagram_content_publish.\n"
                "The Graph API also requires the video to be at a public HTTPS URL —\n"
                "it does not accept direct file uploads — so this adapter needs a\n"
                "hosting step before it can work.\n"
                "Set IG_ACCESS_TOKEN and IG_USER_ID in config/.env."
            )
        raise NotImplementedError(
            "Instagram Reels publishing needs a public URL host for the media; "
            "wire that up before implementing the container/publish calls."
        )


def build_publishers(cfg: Config) -> dict[str, Publisher]:
    available: dict[str, Publisher] = {}
    if cfg.get("publish.youtube.enabled"):
        available["youtube"] = YouTubePublisher(cfg)
    if cfg.get("publish.tiktok.enabled"):
        available["tiktok"] = TikTokPublisher(cfg)
    if cfg.get("publish.instagram.enabled"):
        available["instagram"] = InstagramPublisher(cfg)
    return available


def privacy_for(cfg: Config, platform: str, mode: str) -> str:
    key = {"manual": "privacy_manual", "assisted": "privacy_assisted", "auto": "privacy_auto"}[mode]
    default = {"youtube": "private", "tiktok": "SELF_ONLY", "instagram": "private"}[platform]
    return cfg.get(f"publish.{platform}.{key}", default)


def publish_pair(
    cfg: Config,
    store: Store,
    *,
    longform: dict[str, Any] | None,
    short: dict[str, Any] | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Publish the day's pair, long-form first.

    The short's description is finalised only after the long-form URL is known.
    If the long-form fails to publish, the short is held back rather than posted
    with a dead link — a short with no destination is not a funnel, it is just
    a clip with a broken promise in the caption.
    """
    mode = cfg.require("autonomy.mode")
    report: dict[str, Any] = {"mode": mode, "longform": {}, "short": {}, "skipped": []}

    # Re-publishing uploads a second copy and, because record_publication is an
    # upsert on (clip_id, platform), overwrites the first one's URL — leaving a
    # public video with no row pointing at it. SAFETY_RULES R7 depends on that
    # row existing to action a takedown, so this guard is a safety control, not
    # just tidiness.
    for clip in (longform, short):
        if clip and store.publication_url(clip["clip_id"], "youtube"):
            report["skipped"].append(
                f"{clip['clip_id']} is already published — refusing to upload a duplicate"
            )
            return report

    if mode == "manual":
        report["skipped"].append(
            "autonomy.mode=manual — files rendered to out/review/, nothing published"
        )
        return report

    publishers = build_publishers(cfg)
    if not publishers:
        report["skipped"].append("no platforms enabled in publish.*")
        return report

    longform_url = ""

    if longform:
        yt = publishers.get("youtube")
        if yt is None:
            report["skipped"].append(
                "long-form has no destination — YouTube is the only long-form platform"
            )
        else:
            privacy = privacy_for(cfg, "youtube", mode)
            result = yt.publish(
                Path(longform["file_path"]),
                longform["title"],
                longform["description"],
                privacy,
                tags=cfg.get("packaging.longform.tags", []),
            )
            store.record_publication(
                longform["clip_id"], result.platform, result.remote_id, result.url, result.privacy
            )
            longform_url = result.url
            report["longform"] = {"platform": "youtube", "url": result.url, "privacy": privacy}

    if short:
        if not longform_url:
            report["skipped"].append(
                "short withheld: no long-form URL to point at (the short exists to "
                "route traffic to the full case)"
            )
            return report

        description = cfg.require("packaging.short.description_template").format(
            hook_line=context["hook_line"],
            longform_url=longform_url,
            court=cfg.require("source.court"),
            hashtags=cfg.get("packaging.short.hashtags", ""),
        )
        store.set_clip_description(short["clip_id"], description)

        for name, publisher in publishers.items():
            try:
                privacy = privacy_for(cfg, name, mode)
                result = publisher.publish(
                    Path(short["file_path"]), short["title"], description, privacy
                )
                store.record_publication(
                    short["clip_id"], result.platform, result.remote_id, result.url, result.privacy
                )
                report["short"][name] = {"url": result.url, "privacy": privacy}
            except Exception as exc:
                # One platform must not take down the others — and the failure
                # that matters most is a real API error (googleapiclient's
                # HttpError on quota, an auth RefreshError), not the stub
                # adapters' RuntimeError. Catching only the stubs would let a
                # transient YouTube error skip every remaining platform, which
                # is the exact case this guard exists to prevent.
                report["short"][name] = {
                    "error": f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
                }

    return report
