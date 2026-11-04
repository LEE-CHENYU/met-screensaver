# Mediterranean museum screensaver

A GNOME Wayland screensaver that turns open museum collections into rotating,
themed exhibitions, with short historical context and artistic opening posters.

![Old Kingdom exhibition cover](assets/old-kingdom-cover.png)

The curator draws from The Metropolitan Museum of Art, Cleveland Museum of Art,
Art Institute of Chicago, and licensed Wikimedia Commons images. Seventeen themes
span the Aegean, Greece, Italy, Cyprus, the Levant, Egypt, and Anatolia.

## Viewing experience

Artwork fills the screen without cropping. Every 12 seconds, the next work
crossfades in. A compact bottom overlay combines a paragraph about the period's
society, beliefs, technology, politics, or economics with a short title/date
reference. Its background is 68% transparent, with text shadows for readability.
Keyboard, pointer movement, clicking, or scrolling dismisses the viewer.

The viewer caches original museum images to avoid duplicating labels baked into
older slide JPEGs. New exhibits automatically receive researched context matched
to their theme and object metadata. The repository includes 60 tailored Old Kingdom
paragraphs and a sourced fallback bank covering all 17 themes. Fallback context is
not newly researched evidence about each unseen object.

## Install on an Ubuntu GNOME desktop

Requires Python 3.10+, Pillow, PyGObject, GTK 4, gdbus, GNU coreutils, and systemd.
The actual viewer uses GTK 4; imv is not required.

```bash
sudo apt install python3 python3-pil python3-gi gir1.2-gtk-4.0 libglib2.0-bin
sudo ./install.sh
```

The installer targets the desktop account that invoked sudo. To select another
existing account, use `sudo SCREENSAVER_USER=alice ./install.sh`. It installs code
under `/opt/met-screensaver`, creates `/srv/screensaver/{exhibits,state}`, and writes
system and user units. It does not enable timers or start the slideshow.

Build the first exhibit on the network-enabled desktop:

```bash
sudo systemctl start met-curator.service
sudo journalctl -u met-curator.service -n 50 --no-pager
sudo systemctl enable --now met-curator.timer
```

The weekly timer runs Mondays at 06:00 in local time, with up to 30 minutes of
random delay. It runs as the selected non-root user. From a terminal inside that
user's GNOME session, enable the viewer:

```bash
systemctl --user import-environment WAYLAND_DISPLAY XDG_SESSION_TYPE DISPLAY
systemctl --user daemon-reload
systemctl --user enable --now met-slideshow.service
```

If upgrading an existing installation, inspect `systemctl --user cat
met-slideshow.service`: an old drop-in can override the newly installed ExecStart.
The existing machine used during development has a viewer override under
`~/.local/share/met-screensaver`. Installing this repository does not remove it.

Defaults: five minutes idle, 12 seconds per slide, and images from
`/srv/screensaver/current`. Override `IDLE_MIN`, `SLIDE_SECONDS`, or `IMG_DIR` in a
user service drop-in. GNOME locking, blanking, and power settings are left alone.

## Build and publish an exhibition

```bash
python3 met_curator.py --theme old-kingdom --count 60
python3 met_curator.py --theme mycenaean --count 60 --sources met,cleveland,aic,commons
```

The curator chooses less recently seen themes and objects, bounds API usage,
throttles requests, retries transient failures, backfills failed image downloads,
and applies source/license filters. It requires at least 20 usable works. Commons
is capped at one quarter of selected works and highlights at one third. Duplicate
IDs and near-identical titles within a source are excluded.

Exhibits contain a title slide, numbered object images, `credits.csv`, and
`exhibit.json`. A complete exhibit is built in staging, then published through an
atomic replacement of the `current` symlink. Failed builds leave the previous
exhibit in place. Four managed exhibits are retained; history and seen IDs remain
in `state/history.json`. A state lock prevents overlapping builds.

`--root` and `--state` select alternate directories. `--dry-run` still contacts
museum APIs, but downloads no images and changes no state. Inspect `--help` for
request limits and theme choices. Development tests are offline.

## Covers and standing agent instructions

Read [AGENTS.md](AGENTS.md) before exhibition work. It preserves the owner's
requirements: full-size art, translucent bottom paragraphs, concise title/period
references, historically meaningful writing, source provenance, and poster-style
covers.

Put a 16:9 exhibition poster at `assets/<theme-slug>-cover.png` before building an
exhibit. The curator uses it automatically. The included Old Kingdom cover is a
modern AI-generated Art Deco/Egyptian Revival interpretation incorporating a
carnelian Eye of Horus amulet. It is a designed cover, not an archaeological image.
If no theme cover exists, the curator uses its basic artwork-and-type opening.

The weekly systemd job collects objects and builds slides; it does not run an AI
agent. New custom posters and fresh object-specific research require agent work.
Saving standing instructions does not schedule that work.

## Source files

- `met_curator.py`, `met_fetch.py`, `art_sources.py`: collection, image processing,
  exhibition selection, credits, and atomic publication.
- `idle_slideshow.sh`, `slideshow.py`: GNOME idle monitoring and the GTK viewer.
- `auto_captions.py`, `context-bank.json`: metadata-aware historical context.
- `build_context_bank.py`: maintain/rebuild the context bank and source index.
- `captions.json`, `caption-sources.json`: tailored editorial notes and references.
- `caption_reference.py`: short visible titles and dates, without location tails.
- `clean_images.py`: asynchronous original-image cache in
  `~/.cache/met-screensaver/originals`.
- `examples/old-kingdom/exhibit.json`: public catalog metadata for the sample exhibit.

## Verification

```bash
python3 -m compileall -q .
bash -n install.sh idle_slideshow.sh
python3 -m unittest discover -s tests -v
# GTK integration check (requires an X server or Xvfb):
sudo apt install xvfb
GSK_RENDERER=cairo xvfb-run -a -s '-screen 0 1920x1080x24' python3 tests/viewer_smoke.py
```

## Image rights and provenance

Collection-image licenses remain those of their sources. Met and Cleveland
admitted images use CC0; Chicago images are public domain/CC0. Commons images
must carry an approved explicit Public Domain, CC0, CC BY, or CC BY-SA license.
Full available credits, authors, licenses, and catalog URLs are preserved in each
exhibit's credits and manifest, even when the on-screen reference is abbreviated.
Follow the original file's attribution and share-alike conditions when distributing
its images. Bulk downloaded exhibits and caches are not included in this repository.

Cover reference: [Eye of Horus (Wedjat) Amulet, Art Institute of Chicago](https://www.artic.edu/artworks/135872),
CC0. Sources for the educational captions are recorded in `caption-sources.json`
and `context-sources.json`. No software license has been selected for this repository.
