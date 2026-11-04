#!/usr/bin/env python3
"""Build and atomically publish a weekly exhibit from four open image sources.

Dry runs fetch search/object metadata, but never images or change local state.
All traffic uses the shared throttled met_fetch client; imports are offline.
"""

import argparse
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
import fcntl
from difflib import SequenceMatcher
import http.client
import json
from pathlib import Path
import random
import re
import shutil
import sys
import tempfile
import urllib.parse
import unicodedata
import uuid

from PIL import Image, ImageDraw, ImageFont

import met_fetch as met
from auto_captions import make_caption
from art_sources import ADAPTERS, CLEVELAND_DEPARTMENTS, SOURCE_ORDER, SourceRule, record_key


@dataclass(frozen=True)
class Theme:
    slug: str
    title: str
    subtitle: str
    department_ids: tuple
    search_terms: tuple
    # Every group must match; within a group, any listed field/keyword may match.
    keyword_groups: tuple
    begin_range: tuple = ()
    source_rules: dict = field(default_factory=dict)


THEMES = (
    Theme("cycladic-minoan", "Islands of the Early Aegean",
          "Cycladic forms and Minoan craft reveal the connected worlds of the Bronze Age Aegean.",
          (13,), ("Cycladic", "Minoan"),
          ({"culture": ("Cycladic", "Minoan"), "period": ("Cycladic", "Minoan")},)),
    Theme("mycenaean", "The Mycenaean World",
          "Vessels, ornaments, and images trace the palace cultures of the Late Bronze Age.",
          (13,), ("Mycenaean", "Helladic"),
          ({"culture": ("Mycenaean",), "period": ("Mycenaean", "Helladic")},)),
    Theme("geometric-archaic", "Greece Takes Shape",
          "Geometric patterns and Archaic figures mark changing communities in early Greece.",
          (13,), ("Geometric", "Archaic"),
          ({"culture": ("Greek",), "period": ("Geometric", "Archaic")},), (-900, -480)),
    Theme("athenian-vases", "Stories on Athenian Vases",
          "Black-figure and red-figure painters bring myth and daily life to the surfaces of clay.",
          (13,), ("Attic black-figure", "Attic red-figure"),
          ({"culture": ("Attic", "Athenian"), "period": ("Attic",)},
           {"classification": ("Vase",), "medium": ("terracotta", "clay")},
           {"title": ("black-figure", "red-figure", "black figure", "red figure"),
            "medium": ("black-figure", "red-figure", "black figure", "red figure")}), (-700, -300)),
    Theme("classical-sculpture", "Bodies in Classical Greece",
          "Sculpture explores the human figure through the materials and ideals of Classical Greece.",
          (13,), ("Classical sculpture", "Greek marble", "Greek bronze"),
          ({"culture": ("Greek",), "period": ("Classical",)},
           {"classification": ("Sculpture", "Bronzes", "Terracottas"),
            "title": ("statue", "statuette", "relief", "head", "torso")}), (-480, -323)),
    Theme("hellenistic", "Across the Hellenistic World",
          "Art after Alexander reflects mobile people and shared forms across the eastern Mediterranean.",
          (13,), ("Hellenistic",),
          ({"culture": ("Greek", "Hellenistic"), "period": ("Hellenistic",)},), (-323, -30)),
    Theme("etruscan", "The Etruscan Imagination",
          "Etruscan makers shaped distinctive objects within the exchange networks of ancient Italy.",
          (13,), ("Etruscan",),
          ({"culture": ("Etruscan",), "period": ("Etruscan",)},)),
    Theme("cypriot", "Cyprus at the Crossroads",
          "Cypriot art records an island's encounters with the Aegean and the eastern Mediterranean.",
          (13, 3), ("Cypriot", "Cyprus"),
          ({"culture": ("Cypriot", "Cyprus"), "period": ("Cypriot",)},)),
    Theme("phoenician-levantine", "Ivory and Glass of the Levant",
          "Carved ivories and luminous glass reveal the skill and connections of Levantine workshops.",
          (3, 13), ("Phoenician ivory", "Levantine ivory", "Phoenician glass"),
          ({"culture": ("Phoenician", "Levant", "Levantine", "Canaanite", "Syrian", "Syro-Palestinian"),
            "period": ("Phoenician", "Levant", "Levantine")},
           {"classification": ("Ivory", "Ivories", "Glass"), "medium": ("ivory", "glass")}),
          (-2000, -100)),
    Theme("roman-portraits", "Faces of Rome",
          "Roman portraits present identity and authority through the carefully fashioned human face.",
          (13,), ("Roman portrait",),
          ({"culture": ("Roman",), "period": ("Roman",)},
           {"classification": ("Portrait",), "title": ("portrait", "bust", "head")}), (-100, 400)),
    Theme("roman-luxury", "Rooms and Treasures of Rome",
          "Wall paintings, glass, and precious objects evoke the colors and pleasures of Roman interiors.",
          (13,), ("Roman wall painting", "Roman glass", "Roman jewelry", "Roman silver"),
          ({"culture": ("Roman",), "period": ("Roman",)},
           {"classification": ("Painting", "Glass", "Gold", "Silver", "Gems", "Jewelry"),
            "medium": ("fresco", "glass", "gold", "silver", "sardonyx")}), (-100, 400)),
    Theme("old-kingdom", "Egypt's Old Kingdom",
          "Images and objects illuminate the people and beliefs of Egypt's pyramid age.",
          (10,), ("Old Kingdom",),
          ({"period": ("Old Kingdom",)},)),
    Theme("middle-kingdom", "Egypt's Middle Kingdom",
          "Middle Kingdom works bring new expression to kingship and the lives of individuals.",
          (10,), ("Middle Kingdom",),
          ({"period": ("Middle Kingdom",)},)),
    Theme("new-kingdom-amarna", "Egypt's New Kingdom and Amarna",
          "Royal and everyday objects trace the expansive world of the New Kingdom and its Amarna moment.",
          (10,), ("New Kingdom", "Amarna"),
          ({"period": ("New Kingdom", "Amarna"), "dynasty": ("Dynasty 18", "Dynasty 19", "Dynasty 20")},)),
    Theme("late-ptolemaic", "Egypt in a Changing Mediterranean",
          "Late Period and Ptolemaic works show Egyptian traditions within a changing Mediterranean world.",
          (10,), ("Late Period", "Ptolemaic"),
          ({"period": ("Late Period", "Ptolemaic")},)),
    Theme("egyptian-amulets", "Adornment and Protection in Egypt",
          "Jewelry and amulets join personal beauty with enduring hopes for protection and renewal.",
          (10,), ("amulet", "jewelry", "necklace"),
          ({"classification": ("Jewelry", "Amulet",),
            "title": ("amulet", "necklace", "bracelet", "ring", "pendant", "earring", "pectoral")},),
          (-4000, -30)),
    Theme("anatolia-hittites", "Anatolia and the Hittites",
          "Anatolian and Hittite objects connect the highlands of Asia Minor to neighboring ancient worlds.",
          (3,), ("Anatolian", "Hittite"),
          ({"culture": ("Anatolian", "Hittite", "Hattian"),
            "period": ("Anatolian", "Hittite", "Hattian")},), (-3500, -600)),
)

def topic(*keywords):
    # Search relevance alone is insufficient. Require explicit collection metadata
    # or image description evidence for each group, without trusting broad departments.
    return {name: keywords for name in ("title", "culture", "period", "date", "search_text")}


def material(*keywords):
    return {name: keywords for name in ("title", "classification", "medium", "search_text")}


# Met settings above are unchanged. Other APIs have different vocabularies and
# no Met period/dynasty fields; Commons queries emphasize sites and in-situ art.
# slug: (Cleveland terms, Chicago terms, Commons terms, museum filters, Commons filters, dates)
SOURCE_THEME_RULES = {
    "cycladic-minoan": (("Cycladic", "Minoan"), ("Cycladic", "Minoan"),
        ("Minoan Knossos fresco", "Cycladic Akrotiri fresco"),
        (topic("Cycladic", "Minoan"),), (topic("Cycladic", "Minoan", "Knossos", "Akrotiri"),), ()),
    "mycenaean": (("Mycenaean", "Helladic"), ("Mycenaean", "Helladic"),
        ("Mycenaean Tiryns", "Mycenae archaeological"),
        (topic("Mycenaean", "Helladic"),), (topic("Mycenaean", "Mycenae", "Tiryns"),), ()),
    "geometric-archaic": (("Geometric Greek", "Archaic Greek"), ("Greek Geometric", "Greek Archaic"),
        ("Archaic Greek sculpture", "Geometric Greek pottery"),
        (topic("Greek", "Greece", "Attic", "Corinthian", "Geometric", "Archaic"),),
        (topic("Geometric", "Archaic"), topic("Greek", "Greece", "Attic", "Corinthian")), (-900, -480)),
    "athenian-vases": (("Attic black-figure", "Attic red-figure"), ("Attic black figure", "Attic red figure"),
        ("Attic black-figure vase", "Attic red-figure vase"),
        (topic("Attic", "Athenian", "Athens"), material("black-figure", "red-figure", "black figure", "red figure")),
        (topic("Attic", "Athenian", "Athens"), material("black-figure", "red-figure", "black figure", "red figure")), (-700, -300)),
    "classical-sculpture": (("Greek sculpture", "Greek marble", "Greek bronze"), ("Greek sculpture", "Greek statue"),
        ("Classical Greek sculpture", "Parthenon sculpture"),
        (topic("Greek", "Greece"), material("sculpture", "statue", "statuette", "relief", "head", "torso")),
        (topic("Classical Greek", "Parthenon"), material("sculpture", "statue", "relief", "head", "torso")), (-480, -323)),
    "hellenistic": (("Hellenistic",), ("Hellenistic",), ("Hellenistic Pergamon", "Hellenistic archaeological"),
        (topic("Greek", "Greece", "Hellenistic"),), (topic("Hellenistic", "Pergamon"),), (-323, -30)),
    "etruscan": (("Etruscan",), ("Etruscan",), ("Etruscan Tarquinia fresco", "Etruscan tomb"),
        (topic("Etruscan", "Etruria"),), (topic("Etruscan", "Tarquinia", "Cerveteri"),), ()),
    "cypriot": (("Cypriot", "Cyprus"), ("Cypriot", "Cyprus"), ("ancient Cyprus archaeological", "Cypriot antiquities"),
        (topic("Cypriot", "Cyprus"),), (topic("Cypriot", "Cyprus"), material("ancient", "archaeological", "antiquities")), ()),
    "phoenician-levantine": (("Phoenician ivory", "Levantine glass"), ("Phoenician ivory", "Syrian glass"),
        ("Phoenician ivory", "Phoenician glass"),
        (topic("Phoenician", "Levantine", "Levant", "Canaanite", "Syrian"), material("ivory", "ivories", "glass")),
        (topic("Phoenician", "Levantine", "Canaanite"), material("ivory", "ivories", "glass")), (-2000, -100)),
    "roman-portraits": (("Roman portrait", "Roman bust"), ("Roman portrait", "Roman bust"),
        ("ancient Roman portrait bust",),
        (topic("Roman", "Rome"), material("portrait", "bust", "head")),
        (topic("Roman", "Rome"), material("portrait", "bust", "head")), (-100, 400)),
    "roman-luxury": (("Roman glass", "Roman jewelry", "Roman wall painting"), ("Roman glass", "Roman silver", "Roman fresco"),
        ("Pompeii fresco in situ", "Herculaneum fresco", "Roman glass"),
        (topic("Roman", "Rome"), material("fresco", "glass", "gold", "silver", "jewelry", "wall painting")),
        (topic("Roman", "Pompeii", "Herculaneum"), material("fresco", "glass", "gold", "silver", "wall painting")), (-100, 400)),
    "old-kingdom": (("Old Kingdom", "Egypt"), ("Old Kingdom Egypt",), ("Old Kingdom Egypt", "Giza pyramid", "Saqqara Old Kingdom"),
        (topic("Egypt", "Egyptian", "Old Kingdom"),), (topic("Old Kingdom", "Giza", "Saqqara"),), (-2686, -2181)),
    "middle-kingdom": (("Middle Kingdom", "Egypt"), ("Middle Kingdom Egypt",), ("Middle Kingdom Egypt", "Beni Hasan tomb"),
        (topic("Egypt", "Egyptian", "Middle Kingdom"),), (topic("Middle Kingdom", "Beni Hasan"),), (-2055, -1650)),
    "new-kingdom-amarna": (("New Kingdom", "Amarna", "Egypt"), ("New Kingdom Egypt", "Amarna"),
        ("Amarna archaeological", "New Kingdom Egypt fresco", "Theban tomb painting"),
        (topic("Egypt", "Egyptian", "New Kingdom", "Amarna"),), (topic("New Kingdom", "Amarna", "Theban"),), (-1550, -1069)),
    "late-ptolemaic": (("Late Period", "Ptolemaic", "Egypt"), ("Ptolemaic Egypt", "Late Period Egypt"),
        ("Ptolemaic temple Egypt", "Late Period Egypt"),
        (topic("Egypt", "Egyptian", "Ptolemaic"),), (topic("Ptolemaic", "Late Period"),), (-664, -30)),
    "egyptian-amulets": (("Egypt amulet", "Egypt jewelry"), ("Egypt amulet", "Egypt necklace"),
        ("ancient Egyptian amulet", "ancient Egyptian jewelry"),
        (topic("Egypt", "Egyptian"), material("amulet", "necklace", "bracelet", "ring", "pendant", "earring", "pectoral")),
        (topic("Egypt", "Egyptian"), material("amulet", "necklace", "bracelet", "pendant", "earring", "pectoral")), (-4000, -30)),
    "anatolia-hittites": (("Hittite", "Anatolian"), ("Hittite", "Anatolian"),
        ("Hittite Hattusa archaeological", "Hittite Yazilikaya relief"),
        (topic("Hittite", "Hattian", "Anatolian", "Anatolia"),), (topic("Hittite", "Hattusa", "Yazilikaya"),), (-3500, -600)),
}


def with_source_rules(theme):
    cleveland, aic, commons, groups, commons_groups, dates = SOURCE_THEME_RULES[theme.slug]
    departments = tuple(name for dep, name in ((13, CLEVELAND_DEPARTMENTS[1]),
                                              (10, CLEVELAND_DEPARTMENTS[0]),
                                              (3, CLEVELAND_DEPARTMENTS[0]))
                        if dep in theme.department_ids)
    return replace(theme, source_rules={
        "cleveland": SourceRule(cleveland, groups, tuple(dict.fromkeys(departments)), dates),
        "aic": SourceRule(aic, groups, begin_range=dates),
        "commons": SourceRule(commons, commons_groups),
    })


THEMES = tuple(with_source_rules(theme) for theme in THEMES)

MIN_WORKS = 20
KEEP_EXHIBITS = 4
SOURCE_NAMES = dict(met="The Met", cleveland="Cleveland Museum of Art",
                    aic="Art Institute of Chicago", commons="Wikimedia Commons")
NETWORK_ERRORS = (OSError, ValueError, http.client.HTTPException, Image.DecompressionBombError)


def log(message):
    print(f"[curator] {message}", flush=True)


def week_key(day):
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_start(week):
    if not isinstance(week, str) or not re.fullmatch(r"\d{4}-W\d{2}", week):
        raise ValueError(f"Invalid ISO week: {week!r}")
    year, number = week.split("-W")
    return date.fromisocalendar(int(year), int(number), 1)


def parse_history(value):
    """Validate before using history; corrupt history must never erase the seen set."""
    if (not isinstance(value, dict) or type(value.get("version")) is not int
            or value["version"] not in (1, 2)):
        raise ValueError("history.json must have version=1 or 2 and an exhibits list")
    entries = value.get("exhibits")
    if not isinstance(entries, list):
        raise ValueError("history.json exhibits must be a list")
    migrated = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid history entry")
        week_start(entry.get("week"))
        if not isinstance(entry.get("theme"), str) or not entry["theme"]:
            raise ValueError("Invalid history theme")
        entry = dict(entry)
        if value["version"] == 1:
            ids = entry.pop("object_ids", None)
            if not isinstance(ids, list) or any(type(i) is not int or i <= 0 for i in ids):
                raise ValueError("Invalid history object_ids")
            entry["record_ids"] = [f"met:{i}" for i in ids]
        ids = entry.get("record_ids")
        if not isinstance(ids, list) or any(
                not isinstance(i, str) or not re.fullmatch(r"(?:met|cleveland|aic|commons):[1-9][0-9]*", i)
                for i in ids):
            raise ValueError("Invalid history record_ids")
        migrated.append(entry)
    return migrated


def seen_object_ids(history):
    return {identifier for entry in history for identifier in entry["record_ids"]}


def ordered_themes(history, day, forced=None):
    """LRU rotation, with ISO-week rotation breaking ties reproducibly."""
    monday = day - timedelta(days=day.weekday())
    cutoff = monday - timedelta(weeks=8)
    last = {}
    for entry in history:
        shown = week_start(entry["week"])
        last[entry["theme"]] = max(last.get(entry["theme"], date.min), shown)
    offset = day.isocalendar().week % len(THEMES)
    rotated = THEMES[offset:] + THEMES[:offset]
    tie = {theme.slug: index for index, theme in enumerate(rotated)}
    themes = sorted(THEMES, key=lambda t: (
        last.get(t.slug, date.min) >= cutoff,
        last.get(t.slug, date.min), tie[t.slug],
    ))
    if forced:
        themes.sort(key=lambda t: t.slug != forced)
    return themes


def object_year(value):
    # API zero dates usually mean unknown; do not print a historical year zero.
    if type(value) is int and value != 0:
        return value
    return None


def keyword_matches(text, keyword):
    # Word boundaries keep "ring" from admitting an "offering table".
    # Allow a simple plural for classifications such as Vase/Vases.
    return re.search(r"(?<!\w)" + re.escape(keyword.casefold()) + r"s?(?!\w)",
                     met.clean_text(text).casefold()) is not None


def has_image_url(record):
    for field in ("primaryImage", "primaryImageSmall"):
        try:
            url = urllib.parse.urlsplit(met.clean_text(record.get(field)))
            if url.scheme in ("http", "https") and url.netloc:
                return True
        except ValueError:
            continue
    return False


def matches_theme(record, theme):
    if record.get("isPublicDomain") is not True:
        return False
    if not has_image_url(record):
        return False
    for group in theme.keyword_groups:
        if not any(keyword_matches(record.get(field), keyword)
                   for field, keywords in group.items() for keyword in keywords):
            return False
    if theme.begin_range:
        begin = object_year(record.get("objectBeginDate"))
        if begin is None or not theme.begin_range[0] <= begin <= theme.begin_range[1]:
            return False
    return True


def matches_source_theme(record, rule):
    for group in rule.keyword_groups:
        if not any(keyword_matches(record.get(name), keyword)
                   for name, keywords in group.items() for keyword in keywords):
            return False
    if rule.begin_range:
        begin = record.get("begin_year")
        if begin is None or not rule.begin_range[0] <= begin <= rule.begin_range[1]:
            return False
    return True


def title_fingerprint(title):
    title = unicodedata.normalize("NFKD", met.clean_text(title).casefold())
    return " ".join(re.findall(r"[^\W_]+", "".join(c for c in title if not unicodedata.combining(c))))


def near_title(first, second):
    if first == second:
        return True
    # Avoid conflating distinct numbered objects or very short generic labels.
    if (min(len(first), len(second)) < 16
            or abs(len(first) - len(second)) > max(len(first), len(second)) * 0.12
            or re.findall(r"\d+", first) != re.findall(r"\d+", second)):
        return False
    matcher = SequenceMatcher(None, first, second, autojunk=False)
    return matcher.quick_ratio() >= 0.94 and matcher.ratio() >= 0.94


def dedupe_candidates(candidates, seen):
    unique, titles, keys = [], {}, set()
    # Prefer unseen IDs and larger Commons images when a title has duplicates.
    pool = sorted(candidates, key=lambda c: (record_key(c) in seen,
                  c.get("image_width", 1200) < 1200, record_key(c)))
    for candidate in pool:
        key = record_key(candidate)
        title = title_fingerprint(candidate["title"])
        previous = titles.setdefault(candidate["source"], [])
        if key in keys or any(near_title(title, other) for other in previous):
            continue
        keys.add(key)
        previous.append(title)
        unique.append(candidate)
    return unique


def select_candidates(candidates, seen, count, seed):
    """Mix sources round-robin (fresh works first within each source); quotas use the actual exhibit size:
    no source above half the exhibit, Commons at most a quarter, highlights at most a third. Filling from one
    source first let the Met take every slot."""
    pool = dedupe_candidates(candidates, seen)
    random.Random(seed).shuffle(pool)
    pool.sort(key=lambda c: (record_key(c) in seen, c.get("image_width", 1200) < 1200))
    queues = {source: [c for c in pool if c["source"] == source] for source in SOURCE_ORDER}
    for size in range(min(count, len(pool)), 0, -1):
        caps = {source: max(1, size // 4) if source == "commons" else max(1, (size + 1) // 2) for source in SOURCE_ORDER}
        position = dict.fromkeys(SOURCE_ORDER, 0)
        taken = dict.fromkeys(SOURCE_ORDER, 0)
        selected, highlights = [], 0
        progress = True
        while len(selected) < size and progress:
            progress = False
            for source in SOURCE_ORDER:
                queue = queues[source]
                while taken[source] < caps[source] and position[source] < len(queue):
                    candidate = queue[position[source]]
                    position[source] += 1
                    highlight = candidate.get("is_highlight") is True
                    if highlight and highlights >= size // 3:
                        continue
                    selected.append(candidate)
                    taken[source] += 1
                    highlights += highlight
                    progress = True
                    break
                if len(selected) == size:
                    return selected
        # The other sources ran short: give the remaining slots to any source still holding works (the half cap
        # only exists to make room for the others), keeping the Commons and highlight caps.
        for source in SOURCE_ORDER:
            for candidate in queues[source][position[source]:]:
                if len(selected) == size:
                    return selected
                highlight = candidate.get("is_highlight") is True
                if (source == "commons" and taken[source] >= caps[source]) or (highlight and highlights >= size // 3):
                    continue
                selected.append(candidate)
                taken[source] += 1
                highlights += highlight
        if len(selected) == size:
            return selected
    return []


def chronological_key(candidate):
    begin = candidate.get("begin_year")
    return (begin if begin is not None else float("inf"), record_key(candidate))


def candidate_pool_ready(candidates, seen, count, seed):
    if len(candidates) < max(count * 3, MIN_WORKS):
        return False
    fresh = [candidate for candidate in candidates if record_key(candidate) not in seen]
    return len(select_candidates(fresh, set(), count, seed)) >= count


def date_span(records):
    years = [year for record in records for field in ("begin_year", "end_year")
             if (year := object_year(record.get(field))) is not None]
    if not years:
        return "Date range unavailable"
    first, last = min(years), max(years)
    if first == last:
        return f"c. {abs(first)} {'BCE' if first < 0 else 'CE'}"
    if last < 0:
        return f"c. {abs(first)}–{abs(last)} BCE"
    if first > 0:
        return f"c. {first}–{last} CE"
    return f"c. {abs(first)} BCE–{last} CE"


def title_credit(records):
    used = {record["source"] for record in records}
    return "Images: " + " · ".join(SOURCE_NAMES[source] for source in SOURCE_ORDER if source in used)


def render_title_card(theme, records, day, hero=None):
    """An artwork-led opening, with only the exhibit's own title and introduction."""
    cover = Path(__file__).with_name("assets") / f"{theme.slug}-cover.png"
    if cover.is_file():
        from PIL import ImageOps
        with Image.open(cover) as image:
            return ImageOps.fit(image.convert("RGB"), met.FRAME_SIZE)
    frame = Image.new("RGB", met.FRAME_SIZE, (16, 20, 23))
    draw = ImageDraw.Draw(frame)
    if hero is not None:
        from PIL import ImageOps
        with Image.open(hero) as image:
            artwork = ImageOps.contain(image.convert("RGB"), (1120, 940))
        frame.paste(artwork, (800 + (1120 - artwork.width) // 2, (1080 - artwork.height) // 2))
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", 64)
    except OSError:
        title_font = met.load_caption_font(64)
    title_lines = met.wrap_text(theme.title, draw, title_font, 630, max_lines=4)
    y = 280
    for line in title_lines:
        draw.text((90, y), line, font=title_font, fill=(241, 238, 229))
        y += 82
    body = met.load_caption_font(27)
    for line in met.wrap_text(theme.subtitle, draw, body, 600, max_lines=5):
        draw.text((94, y + 35), line, font=body, fill=(177, 186, 188))
        y += 39
    draw.text((94, 895), date_span(records), font=met.load_caption_font(23), fill=(151, 162, 165))
    for i, line in enumerate(met.wrap_text(title_credit(records), draw, met.load_caption_font(16), 630, max_lines=3)):
        draw.text((94, 960 + i * 23), line, font=met.load_caption_font(16), fill=(127, 138, 141))
    return frame


def search_url(department_id, terms, offset, highlights=False):
    params = {"departmentId": department_id, "hasImages": "true", "isPublicDomain": "true",
              "q": terms, "offset": offset, "limit": met.PAGE_SIZE}
    if highlights:
        params["isHighlight"] = "true"
    return f"{met.API_BASE}/v1.1/search?{urllib.parse.urlencode(params)}"


def search_page(page, offset, previous):
    """Normalize one paginated response, refusing a repeated nonempty page."""
    ids = page.get("objectIDs") or []
    if not isinstance(ids, list):
        raise ValueError("Search objectIDs must be a list")
    valid = list(dict.fromkeys(i for i in ids if type(i) is int and i > 0))
    fresh = [i for i in valid if i not in previous]
    if ids and not fresh:
        raise ValueError("Search pagination repeated a page without new IDs")
    next_offset = offset + len(ids)
    total = page.get("total")
    done = not ids or (type(total) is int and next_offset >= total)
    return fresh, next_offset, done


def gather_met_candidates(client, theme, count, seen, seed, cache, max_search, max_objects):
    stats = dict(search_requests=0, object_requests=0, examined=0, matched=0, failed=0)
    candidates, examined = [], set()
    # One highlight page per query seeds the quota; ordinary queries paginate.
    cursors = [dict(department=dep, terms=term, highlights=highlight, offset=0, ids=set(), done=False)
               for dep in theme.department_ids for term in theme.search_terms for highlight in (False, True)]
    while stats["search_requests"] < max_search and any(not c["done"] for c in cursors):
        for cursor in cursors:
            if cursor["done"]:
                continue
            if stats["search_requests"] >= max_search:
                break
            stats["search_requests"] += 1
            try:
                page = client.get_json(search_url(cursor["department"], cursor["terms"],
                                                  cursor["offset"], cursor["highlights"]))
                ids, cursor["offset"], done = search_page(page, cursor["offset"], cursor["ids"])
                cursor["ids"].update(ids)
                cursor["done"] = done or cursor["highlights"]
            except NETWORK_ERRORS as error:
                stats["failed"] += 1
                cursor["done"] = True
                log(f"Search {theme.slug}/{cursor['terms']} failed: {error}")
                continue
            for object_id in ids:
                if object_id in examined:
                    continue
                if object_id not in cache:
                    if stats["object_requests"] >= max_objects:
                        return candidates, stats
                    stats["object_requests"] += 1
                    try:
                        cache[object_id] = client.get_json(f"{met.API_BASE}/v1/objects/{object_id}")
                    except NETWORK_ERRORS as error:
                        stats["failed"] += 1
                        cache[object_id] = None
                        log(f"Object {object_id} failed: {error}")
                examined.add(object_id)
                stats["examined"] += 1
                record = cache[object_id]
                if record is not None and matches_theme(record, theme):
                    normalized = ADAPTERS["met"].normalize(dict(record, objectID=object_id))
                    if normalized is not None:
                        normalized["department"] = normalized["department"] or met.DEPARTMENTS[cursor["department"]]
                        candidates.append(normalized)
                        stats["matched"] += 1
            # Check once per page, keeping title deduplication off the object hot path.
            # Keep looking past a previously exhausted first page for fresh works.
            if candidate_pool_ready(candidates, seen, count, seed):
                return candidates, stats
    return candidates, stats


def gather_source_candidates(client, source, theme, count, seen, seed, max_search):
    adapter, rule = ADAPTERS[source], theme.source_rules[source]
    stats = dict(search_requests=0, examined=0, matched=0, failed=0)
    candidates, examined = [], set()
    cursors = [dict(terms=term, department=department, offset=0, continuation={}, ids=set(), done=False)
               for term in rule.search_terms for department in (rule.departments or ("",))]
    while stats["search_requests"] < max_search and any(not c["done"] for c in cursors):
        for cursor in cursors:
            if cursor["done"] or stats["search_requests"] >= max_search:
                continue
            stats["search_requests"] += 1
            try:
                response = client.get_json(adapter.search_url(cursor["terms"], cursor["department"], cursor))
                rows, next_cursor, done = adapter.page(response, cursor)
                ids = {str(row.get("pageid" if source == "commons" else "id"))
                       for row in rows if isinstance(row, dict)}
                if rows and not ids - cursor["ids"]:
                    raise ValueError("Search pagination repeated a page without new IDs")
                cursor["ids"].update(ids)
                cursor.update(next_cursor)
                cursor["done"] = done
                for raw in rows:
                    if not isinstance(raw, dict):
                        continue
                    identifier = raw.get("pageid" if source == "commons" else "id")
                    if str(identifier) in examined:
                        continue
                    examined.add(str(identifier))
                    stats["examined"] += 1
                    record = adapter.normalize(raw)
                    if record is not None and matches_source_theme(record, rule):
                        candidates.append(record)
                        stats["matched"] += 1
                # Commons alone cannot form an exhibit under the 25% cap.
                target = max(1, count // 4) if source == "commons" else count
                fresh = [c for c in dedupe_candidates(candidates, seen) if record_key(c) not in seen]
                if len(fresh) >= target * 3:
                    return candidates, stats
            except NETWORK_ERRORS as error:
                stats["failed"] += 1
                cursor["done"] = True
                log(f"Search {source}/{theme.slug}/{cursor['terms']} failed: {error}")
    return candidates, stats


def gather_candidates(client, theme, count, seen, seed, cache, max_search, max_objects, sources):
    candidates, stats = [], {}
    for source in sources:
        if source == "met":
            records, counts = gather_met_candidates(client, theme, count, seen, seed, cache, max_search, max_objects)
        else:
            records, counts = gather_source_candidates(client, source, theme, count, seen, seed, max_search)
        candidates.extend(records)
        stats[source] = dict(counts, candidates=len(dedupe_candidates(records, seen)))
    return candidates, stats


def download_selection(client, candidates, seen, count, seed, staging):
    """Backfill failed images, then number only the final chronological selection."""
    remaining = list(candidates)
    downloaded = {}
    font = met.load_caption_font()
    while True:
        selected = select_candidates(remaining, seen, count, seed)
        if len(selected) < MIN_WORKS:
            return []
        failed = set()
        for candidate in selected:
            key = record_key(candidate)
            if key in downloaded:
                continue
            try:
                frame = met.download_frame(client, candidate, font)
                path = staging / f".work-{key.replace(':', '-')}.jpg"
                met.save_jpeg(path, frame)
                downloaded[key] = path
                log(f"Prepared {key}: {candidate['title']}")
            except NETWORK_ERRORS as error:
                failed.add(key)
                log(f"Image {key} failed; backfilling: {error}")
        if not failed:
            selected.sort(key=chronological_key)
            for index, candidate in enumerate(selected, 1):
                downloaded.pop(record_key(candidate)).rename(staging / slide_name(index, candidate))
            for unused in downloaded.values():
                unused.unlink()
            return selected
        remaining = [c for c in remaining if record_key(c) not in failed]


def slide_name(index, record):
    return f"{index:03d}_{record['source']}-{record['source_id']}.jpg"


def write_json(path, value):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}-", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def exhibit_name(week, slug, existing, suffix):
    base = f"{week}-{slug}"
    # Rebuilding the same theme/week must not replace a directory a viewer uses.
    return base if base not in existing else f"{base}-{suffix}"


def publish(staging, root, current, state, history, entry):
    destination = root / entry["directory"]
    if current.exists() and not current.is_symlink():
        raise ValueError(f"Refusing to replace non-symlink {current}")
    staging.rename(destination)
    link = current.parent / f".current-{uuid.uuid4().hex}"
    history_saved = False
    try:
        link.symlink_to(destination, target_is_directory=True)
        # Persist the full seen set before switching. Restore it if the switch fails.
        write_json(state / "history.json", {"version": 2, "exhibits": history + [entry]})
        history_saved = True
        link.replace(current)
    except BaseException:
        # If a signal arrived just after replace(), retain the now-active directory.
        switched = current.is_symlink() and current.readlink() == destination
        if not switched:
            if history_saved:
                write_json(state / "history.json", {"version": 2, "exhibits": history})
            # This is our newly renamed staging directory, directly in root.
            shutil.rmtree(destination)
        raise
    finally:
        link.unlink(missing_ok=True)
    return destination


def retention_victims(entries, active, keep=KEEP_EXHIBITS):
    """entries are (publication timestamp, basename); always retain the active exhibit."""
    ordered = [name for _, name in sorted(entries, reverse=True)]
    retained = {active}
    for name in ordered:
        if len(retained) >= keep:
            break
        retained.add(name)
    return [name for name in ordered if name not in retained]


def prune_exhibits(root, current):
    entries = []
    for child in root.iterdir():
        if child.is_symlink() or not child.is_dir():
            continue
        try:
            manifest = json.loads((child / "exhibit.json").read_text(encoding="utf-8"))
            if (manifest.get("generator") != "met_curator" or manifest.get("directory") != child.name
                    or not re.fullmatch(r"\d{4}-W\d{2}-[a-z0-9-]+", child.name)):
                continue
            stamp = datetime.fromisoformat(manifest["published_at"])
            if stamp.tzinfo is None:
                continue
            entries.append((stamp.timestamp(), child.name))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    active = current.resolve(strict=True).name
    for name in retention_victims(entries, active):
        path = root / name
        if not path.is_symlink() and path.resolve(strict=True).parent == root:
            shutil.rmtree(path)
            log(f"Removed older exhibit: {name}")


def run(args, history):
    today = date.today()
    week = week_key(today)
    seen = seen_object_ids(history)
    client, cache = met.Client(), {}
    for theme in ordered_themes(history, today, args.theme):
        seed = f"{week}:{theme.slug}"
        log(f"Considering {theme.slug}: {theme.title}")
        candidates, stats = gather_candidates(client, theme, args.count, seen, seed, cache,
                                               args.max_search_requests, args.max_object_requests, args.sources)
        selected = select_candidates(candidates, seen, args.count, seed)
        fresh = sum(record_key(c) not in seen for c in selected)
        highlights = sum(c.get("is_highlight") is True for c in selected)
        log("; ".join(f"{source}: candidates={stats[source]['candidates']}, "
                      f"selected={sum(c['source'] == source for c in selected)}" for source in args.sources))
        log(f"{theme.slug}: {stats}; selectable={len(selected)}, unseen={fresh}, highlights={highlights}")
        if len(selected) < MIN_WORKS:
            log(f"Skipping {theme.slug}: fewer than {MIN_WORKS} usable candidates")
            continue
        if args.dry_run:
            log(f"DRY RUN chosen={theme.slug}, works={len(selected)}; no images downloaded or state changed")
            return 0
        with tempfile.TemporaryDirectory(dir=args.root, prefix=".building-") as temporary:
            staging = Path(temporary)
            selected = download_selection(client, candidates, seen, args.count, seed, staging)
            if len(selected) < MIN_WORKS:
                log(f"Skipping {theme.slug}: fewer than {MIN_WORKS} images survived downloading")
                continue
            now = datetime.now(timezone.utc)
            name = exhibit_name(week, theme.slug, {p.name for p in args.root.iterdir()},
                                now.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
            records = selected
            entry = dict(week=week, theme=theme.slug, record_ids=[record_key(c) for c in selected],
                         directory=name, published_at=now.isoformat())
            met.save_jpeg(staging / "000_title.jpg", render_title_card(theme, records, today, hero=staging / slide_name(1, records[0])))
            met.write_credits(staging / "credits.csv", {
                record_key(c): met.credit_row(record_key(c), c) for c in selected
            })
            write_json(staging / "exhibit.json", dict(
                entry, generator="met_curator", version=2, title=theme.title, subtitle=theme.subtitle,
                theme_definition=asdict(theme), date_span=date_span(records), count=len(selected),
                attribution=title_credit(records), licences=sorted({c['licence'] for c in selected}),
                sources=[source for source in SOURCE_ORDER if any(c['source'] == source for c in selected)],
                search_counts=stats,
                objects=[dict(record_id=record_key(c), source=c['source'], source_id=c['source_id'],
                              slide=slide_name(index, c), metadata=c,
                              caption=make_caption(c, theme=theme.slug, record_id=record_key(c)))
                         for index, c in enumerate(selected, 1)],
            ))
            destination = publish(staging, args.root, args.root.parent / "current",
                                  args.state, history, entry)
        log(f"Published {len(selected)} works: {destination}; current switched atomically")
        try:
            prune_exhibits(args.root, args.root.parent / "current")
        except OSError as error:
            log(f"Exhibit is published; older-exhibit cleanup failed: {error}")
        return 0
    log("FAILED: no theme produced 20 usable works; current was not changed")
    return 1


def parse_sources(value):
    requested = [name.strip() for name in value.split(",")]
    if not requested or any(name not in SOURCE_ORDER for name in requested):
        raise argparse.ArgumentTypeError("sources must be a comma-separated subset of met,cleveland,aic,commons")
    return tuple(source for source in SOURCE_ORDER if source in requested)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/srv/screensaver/exhibits"),
                        help="exhibit directory; current symlink lives in its parent")
    parser.add_argument("--state", type=Path, default=Path("/srv/screensaver/state"))
    parser.add_argument("--count", type=met.positive_int, default=60, help="desired works (minimum 20)")
    parser.add_argument("--theme", choices=[theme.slug for theme in THEMES], help="try this theme first")
    parser.add_argument("--sources", type=parse_sources, default=SOURCE_ORDER,
                        help="enabled sources, comma-separated (default: met,cleveland,aic,commons)")
    parser.add_argument("--dry-run", action="store_true", help="metadata only; do not download images or write state")
    parser.add_argument("--max-search-requests", type=met.positive_int, default=32,
                        help="per-source, per-theme search-call cap")
    parser.add_argument("--max-object-requests", type=met.positive_int, default=500,
                        help="per-theme Met object-call cap (other APIs include metadata in searches)")
    args = parser.parse_args()
    if args.count < MIN_WORKS:
        parser.error("--count must be at least 20")
    args.root = args.root.expanduser().resolve()
    args.state = args.state.expanduser().resolve()
    lock = None
    try:
        if not args.dry_run:
            args.state.mkdir(parents=True, exist_ok=True)
            args.root.mkdir(parents=True, exist_ok=True)
            lock = (args.state / ".curator.lock").open("a")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                log("FAILED: another curator run holds the state lock")
                return 1
        path = args.state / "history.json"
        history = parse_history(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else []
        return run(args, history)
    except KeyboardInterrupt:
        log("Interrupted")
        return 130
    except (OSError, ValueError, http.client.HTTPException) as error:
        log(f"FAILED: {error}")
        return 1
    finally:
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    sys.exit(main())
