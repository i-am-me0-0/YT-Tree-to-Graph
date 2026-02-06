import re
import html

YOUTUBE_RE = re.compile(r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})')


def parse_description(text):
    """Parse YouTube links from description HTML or plain text.

    Prefer anchor text when HTML is present (handles links like `/watch?v=ID`).
    Falls back to extracting video ids from plain text.
    Returns list of {'video_id': id, 'text': label}.
    """
    choices = []
    if not text:
        return choices

    # Try to extract from anchor tags first (handles YouTube's HTML snippet)
    # Matches href variants: /watch?v=..., https://youtube.com/watch?v=..., youtu.be/...
    a_re = re.compile(r'<a[^>]+href=["\'](?:https?://(?:www\.)?youtube\.com/watch\?v=|/watch\?v=|https?://youtu\.be/|youtu\.be/)([A-Za-z0-9_-]{11})[^"\']*["\'][^>]*>(.*?)</a>', re.I | re.S)
    for m in a_re.finditer(text):
        vid = m.group(1)
        inner = m.group(2)
        # strip any inner tags and collapse whitespace
        label = re.sub(r'<[^>]+>', '', inner)
        label = html.unescape(label).strip()
        label = re.sub(r'\s+', ' ', label)
        # remove leading bullets/markers and non-printables
        label = label.strip('\u2022\u00A0 \t\n\r-–—:')
        choices.append({'video_id': vid, 'text': label})

    # If no anchors found, fall back to plain-text URL extraction
    if not choices:
        for m in YOUTUBE_RE.finditer(text):
            vid = m.group(1)
            choices.append({'video_id': vid, 'text': ''})

    return choices
