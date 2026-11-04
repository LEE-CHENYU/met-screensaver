"""Small adapters for open collection metadata; importing never makes requests.

Adapters return the same record shape. Extra classification/medium/search_text
fields support local theme filtering without inventing missing historical dates.
"""

from dataclasses import dataclass
from html.parser import HTMLParser
import re
import urllib.parse

import met_fetch as met


SOURCE_ORDER = ("met", "cleveland", "aic", "commons")
CLEVELAND_DEPARTMENTS = ("Egyptian and Ancient Near Eastern Art", "Greek and Roman Art")


@dataclass(frozen=True)
class SourceRule:
    search_terms: tuple
    keyword_groups: tuple
    departments: tuple = ()
    begin_range: tuple = ()


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        elif tag in ("br", "p", "div", "li"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        elif tag in ("p", "div", "li"):
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def strip_html(value):
    parser = _PlainText()
    parser.feed(met.clean_text(value))
    return met.clean_text("".join(parser.parts))


def http_url(value):
    value = met.clean_text(value)
    try:
        parts = urllib.parse.urlsplit(value)
        return value if parts.scheme in ("https", "http") and parts.netloc else ""
    except ValueError:
        return ""


def year(value):
    return value if type(value) is int and value != 0 else None


def source_id(value):
    if type(value) is int and value > 0:
        return str(value)
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        return value
    return ""


def record_key(record):
    return f"{record['source']}:{record['source_id']}"


def commons_licence(value):
    """Deliberately narrow allowlist; never infer a licence from a URL or credit."""
    value = strip_html(value)
    if value.casefold() == "public domain":
        return "Public domain"
    if re.fullmatch(r"CC0(?: 1\.0)?", value, re.IGNORECASE):
        return value.upper()
    match = re.fullmatch(r"CC (BY(?:-SA)?) (1\.0|2\.0|2\.5|3\.0|4\.0)", value, re.IGNORECASE)
    return f"CC {match[1].upper()} {match[2]}" if match else ""


def _record(source, identifier, **fields):
    identifier = source_id(identifier)
    if not identifier or not http_url(fields.get("image_url")):
        return None
    record = dict(source=source, source_id=identifier, title="Untitled", culture="", period="",
                  date="", begin_year=None, end_year=None, department="", page_url="",
                  credit="", licence="CC0", author="", is_highlight=False)
    record.update(fields)
    return record


class MetAdapter:
    source = "met"

    @staticmethod
    def normalize(raw):
        if raw.get("isPublicDomain") is not True:
            return None
        image = http_url(raw.get("primaryImage")) or http_url(raw.get("primaryImageSmall"))
        return _record("met", raw.get("objectID"), title=met.clean_text(raw.get("title")) or "Untitled",
                       culture=met.clean_text(raw.get("culture")), period=met.clean_text(raw.get("period")),
                       date=met.clean_text(raw.get("objectDate")),
                       begin_year=year(raw.get("objectBeginDate")), end_year=year(raw.get("objectEndDate")),
                       department=met.clean_text(raw.get("department")), image_url=image,
                       image_url_small=http_url(raw.get("primaryImageSmall")),
                       page_url=http_url(raw.get("objectURL")), credit=met.clean_text(raw.get("creditLine")),
                       author=met.clean_text(raw.get("artistDisplayName")),
                       is_highlight=raw.get("isHighlight") is True)


class ClevelandAdapter:
    source = "cleveland"
    page_size = 100

    @classmethod
    def search_url(cls, terms, department, cursor):
        params = dict(q=terms, department=department, cc0=1, has_image=1,
                      limit=cls.page_size, skip=cursor["offset"])
        return "https://openaccess-api.clevelandart.org/api/artworks/?" + urllib.parse.urlencode(params)

    @classmethod
    def page(cls, response, cursor):
        rows = response.get("data", [])
        if not isinstance(rows, list):
            raise ValueError("Cleveland data must be a list")
        offset = cursor["offset"] + len(rows)
        total = response.get("info", {}).get("total")
        return rows, dict(offset=offset), not rows or (type(total) is int and offset >= total)

    @staticmethod
    def normalize(raw):
        if met.clean_text(raw.get("share_license_status")).upper() != "CC0":
            return None
        images = raw.get("images") or {}
        image = http_url((images.get("web") or {}).get("url"))
        fallback = http_url((images.get("print") or {}).get("url"))
        cultures = raw.get("culture") or []
        culture = "; ".join(met.clean_text(c) for c in cultures) if isinstance(cultures, list) else met.clean_text(cultures)
        return _record("cleveland", raw.get("id"), title=met.clean_text(raw.get("title")) or "Untitled",
                       culture=culture, date=met.clean_text(raw.get("creation_date")),
                       begin_year=year(raw.get("creation_date_earliest")),
                       end_year=year(raw.get("creation_date_latest")),
                       department=met.clean_text(raw.get("department")), image_url=image or fallback,
                       image_url_small=fallback, page_url=http_url(raw.get("url")),
                       credit=met.clean_text(raw.get("creditline")),
                       classification=met.clean_text(raw.get("type")), medium=met.clean_text(raw.get("technique")))


class AICAdapter:
    source = "aic"
    page_size = 100
    fields = ("id,title,department_title,image_id,is_public_domain,date_start,date_end,date_display,"
              "place_of_origin,artist_display,medium_display,credit_line,classification_title")

    @classmethod
    def search_url(cls, terms, department, cursor):
        params = dict(q=terms, limit=cls.page_size, page=cursor["offset"] + 1, fields=cls.fields)
        return "https://api.artic.edu/api/v1/artworks/search?" + urllib.parse.urlencode(params)

    @classmethod
    def page(cls, response, cursor):
        rows = response.get("data", [])
        if not isinstance(rows, list):
            raise ValueError("Chicago data must be a list")
        page = cursor["offset"] + 1
        received = cursor.get("received", 0) + len(rows)
        pagination = response.get("pagination", {})
        total = pagination.get("total")
        # Missing totals fall back to an empty page, bounded by the search budget.
        done = not rows or (type(total) is int and received >= total)
        return rows, dict(offset=page, received=received), done

    @staticmethod
    def normalize(raw):
        image_id = met.clean_text(raw.get("image_id"))
        if raw.get("is_public_domain") is not True or not image_id:
            return None
        image = "https://www.artic.edu/iiif/2/" + urllib.parse.quote(image_id, safe="") + "/full/1686,/0/default.jpg"
        identifier = source_id(raw.get("id"))
        return _record("aic", identifier, title=met.clean_text(raw.get("title")) or "Untitled",
                       culture=met.clean_text(raw.get("place_of_origin")),
                       date=met.clean_text(raw.get("date_display")),
                       begin_year=year(raw.get("date_start")), end_year=year(raw.get("date_end")),
                       department=met.clean_text(raw.get("department_title")), image_url=image,
                       page_url=f"https://www.artic.edu/artworks/{identifier}",
                       credit=met.clean_text(raw.get("credit_line")), author=met.clean_text(raw.get("artist_display")),
                       search_text=met.clean_text(raw.get("artist_display")),
                       classification=met.clean_text(raw.get("classification_title")),
                       medium=met.clean_text(raw.get("medium_display")))


class CommonsAdapter:
    source = "commons"
    page_size = 50

    @classmethod
    def search_url(cls, terms, department, cursor):
        params = dict(action="query", format="json", generator="search", gsrnamespace=6,
                      gsrsearch=terms + " filetype:bitmap", gsrlimit=cls.page_size,
                      prop="imageinfo", iiprop="url|size|extmetadata", iiurlwidth=1920)
        params.update(cursor.get("continuation", {}))
        return "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)

    @staticmethod
    def page(response, cursor):
        if "error" in response:
            raise ValueError(f"Commons API error: {response['error']}")
        pages = response.get("query", {}).get("pages", {})
        if not isinstance(pages, dict):
            raise ValueError("Commons pages must be an object")
        continuation = response.get("continue") or {}
        if not isinstance(continuation, dict):
            raise ValueError("Commons continuation must be an object")
        return list(pages.values()), dict(continuation=continuation), not continuation

    @staticmethod
    def normalize(raw):
        infos = raw.get("imageinfo") or []
        if not isinstance(infos, list) or not infos or not isinstance(infos[0], dict):
            return None
        info = infos[0]
        metadata = info.get("extmetadata") or {}

        def text(name):
            value = metadata.get(name) or {}
            return strip_html(value.get("value")) if isinstance(value, dict) else ""

        licence = commons_licence(text("LicenseShortName"))
        if not licence:
            return None
        filename = met.clean_text(raw.get("title"))
        title = text("ObjectName") or re.sub(r"\.[^.]+$", "", filename.removeprefix("File:")).replace("_", " ")
        image = http_url(info.get("thumburl")) or http_url(info.get("url"))
        width = info.get("thumbwidth") if http_url(info.get("thumburl")) else info.get("width")
        return _record("commons", raw.get("pageid"), title=title or "Untitled", image_url=image,
                       image_width=width if type(width) is int else 0,
                       page_url=http_url(info.get("descriptionurl")) or
                       "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(filename.replace(" ", "_")),
                       department=text("Collection") or "Wikimedia Commons", licence=licence,
                       author=text("Artist") or text("Credit") or "Unknown author", credit=text("Credit"),
                       date=("Image date: " + text("Date")) if text("Date") else "",
                       search_text=" ".join((filename, title, text("ImageDescription"), text("Categories"))))


ADAPTERS = {adapter.source: adapter for adapter in (MetAdapter, ClevelandAdapter, AICAdapter, CommonsAdapter)}
