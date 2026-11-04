#!/usr/bin/env python3
"""Fetch Met Open Access highlights and prepare captioned 1920x1080 JPEGs.

Requires Python 3 and Pillow. --limit caps NEW images saved in this run;
existing JPEGs do not consume the limit. Search uses the paginated v1.1 API.
"""

import argparse
import csv
import http.client
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps


API_BASE = "https://collectionapi.metmuseum.org/public/collection"
DEPARTMENTS = {
    13: "Greek and Roman Art",
    10: "Egyptian Art",
    3: "Ancient West Asian Art",
}
MEDITERRANEAN_KEYWORDS = (
    "Phoenician", "Cypriot", "Levant", "Canaanite", "Hittite", "Anatolian",
    "Minoan", "Mycenaean", "Aegean", "Cycladic", "Etruscan", "Mesopotamian",
)
FRAME_SIZE = (1920, 1080)
PAGE_SIZE = 100
USER_AGENT = (
    "PompeiiWeeklyExhibit/2.0 "
    "(personal educational display; open museum collections and licensed Commons images)"
)
LEGACY_CREDIT_FIELDS = (
    "objectID", "title", "culture", "period", "date", "department",
    "objectURL", "creditLine",
)
CREDIT_FIELDS = LEGACY_CREDIT_FIELDS + ("source", "source_id", "page_url", "licence", "author")
SOURCE_CREDITS = {
    "met": "The Met · Open Access (CC0)",
    "cleveland": "Cleveland Museum of Art · Open Access (CC0)",
    "aic": "Art Institute of Chicago · Public domain (CC0)",
}


def clean_text(value):
    """Normalize optional scalar metadata, including embedded newlines."""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    return " ".join(str(value).split())


def is_selected(record, department_id):
    if record.get("isPublicDomain") is not True or not clean_text(record.get("primaryImage")):
        return False
    if department_id != 3:
        return department_id in DEPARTMENTS
    context = " ".join(clean_text(record.get(key)) for key in ("culture", "period")).casefold()
    return any(keyword.casefold() in context for keyword in MEDITERRANEAN_KEYWORDS)


def caption_metadata(record):
    title = clean_text(record.get("title")) or "Untitled"
    details = []
    for key in ("culture", "period"):
        value = clean_text(record.get(key))
        if value and value not in details:
            details.append(value)
    context = " / ".join(details)
    date = clean_text(record.get("date", record.get("objectDate")))
    description = ", ".join(part for part in (context, date) if part)
    return title + (" — " + description if description else "")


def caption_attribution(record):
    source = record.get("source", "met")
    if source != "commons":
        return SOURCE_CREDITS[source]
    author = clean_text(record.get("author")) or "Unknown author"
    if len(author) > 72:
        author = author[:69].rsplit(" ", 1)[0] or author[:69]
        author += "…"
    return f"{author} · {record['licence']} · Wikimedia Commons"


def credit_row(object_id, record, department_id=None):
    source = record.get("source", "met")
    page_url = clean_text(record.get("page_url", record.get("objectURL")))
    return {
        "objectID": str(object_id),
        "title": clean_text(record.get("title")),
        "culture": clean_text(record.get("culture")),
        "period": clean_text(record.get("period")),
        "date": clean_text(record.get("date", record.get("objectDate"))),
        "department": clean_text(record.get("department")) or DEPARTMENTS.get(department_id, ""),
        "objectURL": page_url,
        "creditLine": clean_text(record.get("credit", record.get("creditLine"))),
        "source": source,
        "source_id": str(record.get("source_id", object_id)),
        "page_url": page_url,
        "licence": clean_text(record.get("licence")) or "CC0",
        "author": clean_text(record.get("author", record.get("artistDisplayName"))),
    }


def letterbox(source):
    """Honor EXIF orientation, shrink to fit, and center without cropping/upscaling."""
    image = ImageOps.exif_transpose(source).convert("RGB")
    image.thumbnail(FRAME_SIZE, Image.Resampling.LANCZOS)
    frame = Image.new("RGB", FRAME_SIZE, "black")
    frame.paste(image, ((FRAME_SIZE[0] - image.width) // 2,
                       (FRAME_SIZE[1] - image.height) // 2))
    return frame


def load_caption_font(size=22):
    """Load the shared display font; callers may request title-card sizes."""
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def wrap_text(text, draw, font, width, max_lines=2):
    """Wrap even unbroken titles; cap metadata so the caption stays small."""
    lines = []
    remaining = clean_text(text)
    while remaining and len(lines) < max_lines:
        if draw.textlength(remaining, font=font) <= width:
            lines.append(remaining)
            remaining = ""
            break
        low, high = 1, len(remaining)
        while low < high:
            middle = (low + high + 1) // 2
            if draw.textlength(remaining[:middle], font=font) <= width:
                low = middle
            else:
                high = middle - 1
        cut = remaining.rfind(" ", 0, low + 1)
        cut = cut if cut > 0 else low
        lines.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def caption_lines(record, draw, font, width=1500):
    lines = wrap_text(caption_metadata(record), draw, font, width)
    # Preserve the full attribution even when exceptionally long metadata is cut.
    attribution = caption_attribution(record)
    suffix = " · " + attribution
    if draw.textlength(lines[-1] + suffix, font=font) <= width:
        lines[-1] += suffix
    else:
        lines.extend(wrap_text("· " + attribution, draw, font, width))
    return lines


def render_frame(source, record, font):
    frame = letterbox(source)
    overlay = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    lines = caption_lines(record, draw, font)
    line_height, margin, padding = 29, 24, 10
    width = int(max(draw.textlength(line, font=font) for line in lines))
    top = FRAME_SIZE[1] - margin - len(lines) * line_height - 2 * padding
    draw.rectangle((margin, top, margin + width + 2 * padding,
                    FRAME_SIZE[1] - margin), fill=(0, 0, 0, 170))
    for index, line in enumerate(lines):
        draw.text((margin + padding, top + padding + index * line_height),
                  line, font=font, fill=(230, 230, 230, 255))
    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


class RateLimiter:
    def __init__(self):
        self.next_request = 0.0

    def wait(self):
        time.sleep(max(0.0, self.next_request - time.monotonic()))
        # Slightly over 250 ms keeps all requests below four per second.
        self.next_request = time.monotonic() + 0.26


class PoliteRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, limiter):
        super().__init__()
        self.limiter = limiter

    def redirect_request(self, request, response, code, message, headers, new_url):
        redirected = super().redirect_request(request, response, code, message, headers, new_url)
        if redirected is not None:
            self.limiter.wait()
        return redirected


def request_headers(url):
    headers = {"User-Agent": USER_AGENT}
    if urllib.parse.urlsplit(url).hostname in ("api.artic.edu", "www.artic.edu"):
        headers["AIC-User-Agent"] = USER_AGENT
    return headers


class Client:
    def __init__(self):
        self.limiter = RateLimiter()
        self.opener = urllib.request.build_opener(PoliteRedirectHandler(self.limiter))

    def get_bytes(self, url):
        if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
            raise ValueError("Image/API URL must use HTTP or HTTPS")
        for attempt in range(4):  # Initial attempt plus three retries.
            self.limiter.wait()
            request = urllib.request.Request(url, headers=request_headers(url))
            retry_after = 0.0
            try:
                with self.opener.open(request, timeout=45) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                if error.code not in (408, 425, 429, 500, 502, 503, 504) or attempt == 3:
                    error.close()
                    raise
                header = error.headers.get("Retry-After", "")
                try:
                    retry_after = max(0.0, float(header))
                except ValueError:
                    try:
                        retry_after = max(0.0, parsedate_to_datetime(header).timestamp() - time.time())
                    except (TypeError, ValueError, OverflowError):
                        pass
                error.close()
                reason = f"HTTP {error.code}"
            except (OSError, http.client.HTTPException) as error:
                if attempt == 3:
                    raise
                reason = str(error)
            delay = max(2 ** attempt, retry_after)
            print(f"Retry {attempt + 1}/3 in {delay:g}s: {reason}", file=sys.stderr)
            time.sleep(delay)

    def get_json(self, url):
        value = json.loads(self.get_bytes(url))
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value


def department_object_ids(client, department_id):
    offset = 0
    seen = set()
    while True:
        query = urllib.parse.urlencode({
            "departmentId": department_id, "hasImages": "true",
            "isHighlight": "true", "q": "*", "offset": offset, "limit": PAGE_SIZE,
        })
        page = client.get_json(f"{API_BASE}/v1.1/search?{query}")
        ids = page.get("objectIDs") or []
        if not isinstance(ids, list):
            raise ValueError("Search objectIDs must be a list")
        if not ids:
            return
        fresh = False
        for object_id in ids:
            if type(object_id) is int and object_id > 0 and object_id not in seen:
                seen.add(object_id)
                fresh = True
                yield object_id
        if not fresh:
            raise ValueError("Search pagination repeated a page without new IDs")
        offset += len(ids)
        total = page.get("total")
        if isinstance(total, int) and offset >= total:
            return


def read_credits(path):
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return parse_credit_rows(reader.fieldnames, reader)


def parse_credit_rows(fieldnames, entries):
    """Upgrade standalone Met CSV rows without discarding multi-source credits."""
    if not set(LEGACY_CREDIT_FIELDS).issubset(fieldnames or []):
        raise ValueError("Unexpected CSV header; refusing to overwrite it")
    rows = {}
    for entry in entries:
        row = dict(entry)
        if row.get("source", "met") not in ("met", "") or ":" in row.get("objectID", ""):
            raise ValueError("Standalone Met fetcher cannot resume a multi-source credits.csv")
        if not row.get("objectID", "").isdigit():
            continue
        row.update(source="met", source_id=row["objectID"],
                   page_url=row.get("page_url") or row.get("objectURL", ""),
                   licence=row.get("licence") or "CC0", author=row.get("author", ""))
        rows[row["objectID"]] = {key: row.get(key, "") for key in CREDIT_FIELDS}
    return rows


def write_credits(path, rows):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=path.parent, prefix=".credits-", delete=False) as handle:
            temporary = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=CREDIT_FIELDS)
            writer.writeheader()
            writer.writerows(rows[key] for key in sorted(rows, key=lambda key: (
                0, int(key)) if key.isdigit() else (1, key)))
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_jpeg(path, frame):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".met-", delete=False) as handle:
            temporary = Path(handle.name)
            frame.save(handle, format="JPEG", quality=90)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def download_frame(client, record, font):
    urls = []
    for key in ("image_url", "image_url_small", "primaryImage", "primaryImageSmall"):
        url = clean_text(record.get(key))
        if url and url not in urls:
            urls.append(url)
    for index, url in enumerate(urls):
        try:
            with Image.open(io.BytesIO(client.get_bytes(url))) as source:
                return render_frame(source, record, font)
        except (OSError, ValueError, http.client.HTTPException, Image.DecompressionBombError) as error:
            if index == len(urls) - 1:
                raise
            print(f"Full-size image failed; trying primaryImageSmall: {error}", file=sys.stderr)
    raise ValueError("No image URL")


@dataclass
class Counts:
    saved: int = 0
    existing: int = 0
    filtered: int = 0
    failed: int = 0


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="output JPEG/credits directory")
    parser.add_argument("--limit", type=positive_int, help="maximum NEW JPEGs saved this run")
    args = parser.parse_args()
    counts = {department_id: Counts() for department_id in DEPARTMENTS}
    saved = 0
    status = 0
    limited = False
    try:
        args.out.mkdir(parents=True, exist_ok=True)
        credits_path = args.out / "credits.csv"
        credits = read_credits(credits_path)
        write_credits(credits_path, credits)  # A header exists even if nothing qualifies.
        client = Client()
        font = load_caption_font()
        for department_id in DEPARTMENTS:
            stats = counts[department_id]
            try:
                for object_id in department_object_ids(client, department_id):
                    path = args.out / f"{object_id}.jpg"
                    exists = path.is_file()
                    if exists and str(object_id) in credits:
                        stats.existing += 1
                        continue
                    try:
                        record = client.get_json(f"{API_BASE}/v1/objects/{object_id}")
                        if not is_selected(record, department_id):
                            stats.filtered += 1
                            continue
                        # Repair missing credits on resume without re-downloading the JPEG.
                        frame = None if exists else download_frame(client, record, font)
                    except (OSError, ValueError, http.client.HTTPException,
                            Image.DecompressionBombError) as error:
                        stats.failed += 1
                        status = 1
                        print(f"Object {object_id} failed: {error}", file=sys.stderr)
                        continue
                    if exists:
                        stats.existing += 1
                    else:
                        save_jpeg(path, frame)
                        stats.saved += 1
                        saved += 1
                        print(f"Saved {path.name}: {clean_text(record.get('title'))}", flush=True)
                    credits[str(object_id)] = credit_row(object_id, record, department_id)
                    write_credits(credits_path, credits)
                    if args.limit is not None and saved >= args.limit:
                        limited = True
                        break
            except (OSError, ValueError, http.client.HTTPException) as error:
                stats.failed += 1
                status = 1
                print(f"Department {department_id} stopped: {error}", file=sys.stderr)
            if limited:
                break
    except KeyboardInterrupt:
        print("Interrupted; completed images and credits are retained.", file=sys.stderr)
        status = 130
    except (OSError, ValueError) as error:
        print(f"Fetch stopped: {error}", file=sys.stderr)
        status = 1
    finally:
        details = "; ".join(
            f"{name} ({department_id}): saved={stats.saved}, existing={stats.existing}, "
            f"filtered={stats.filtered}, failed={stats.failed}"
            for department_id, name in DEPARTMENTS.items()
            for stats in (counts[department_id],)
        )
        print("Summary: " + details + ("; new-image limit reached" if limited else ""), flush=True)
    return status


if __name__ == "__main__":
    sys.exit(main())
