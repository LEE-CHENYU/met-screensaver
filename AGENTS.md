# Screensaver: standing user preferences

These requirements were explicitly established by the owner. Apply them to new
exhibitions and future screensaver changes without asking the owner to repeat them.

## Exhibition experience

- Show the artwork at full-screen contain size. Caption widgets must overlay the
  image, never reserve space above or below it or make the artwork smaller.
- Put historical context and identification together in one compact bottom block.
  Use a dark background at approximately 32% opacity (68% transparent), white text
  with a subtle shadow, and comfortable padding. Keep the picture visible through it.
- The reference contains only a concise object title and date/time period. Remove
  locations, museum names, photographer/file identifiers, and long catalog tails
  from this visible reference. Retain full attribution, licenses, catalog links,
  and research provenance in the manifest/credits/source files.
- Avoid showing both a baked-in catalog label and a second live reference. Use the
  cached original museum image through clean_images.py. The opaque loading fallback
  is temporary while an uncached original downloads.
- The normal slide duration is 12 seconds. Context should be a compact paragraph
  of roughly 25–35 words, normally 2–4 lines, expressing one clear historical idea.
  Never truncate it mid-argument just to meet a line count.

## What captions teach

Explain what objects reveal about history, culture, social organization,
technology, anthropology, and economics. Across an exhibit, vary the lens: labor,
trade, administration, power, belief, family, status, production, materials, and
technical knowledge. Do not revert to descriptions of shapes or generic prompts
such as “look closely” and “notice the surface.”

Research object-specific claims using museum collection entries, university
research, excavation reports, or other primary scholarly sources. Save the source
URLs. Distinguish facts, wider period context, plausible interpretation, and
uncertainty. Never infer an exact use, identity, ethnic group, trade route, or
historical event from an image alone. Keep culture and chronology matched:
Ptolemaic claims do not automatically apply to Late Period objects, nor Hittite
imperial claims to earlier Anatolian objects. auto_captions.py and context-bank.json
provide researched fallback paragraphs, not fresh research about unseen objects.

For a new exhibition, supply tailored editorial notes in captions.json keyed by
source:id (and corresponding caption-sources.json entries), or manifest caption
fields. Check all selected objects have meaningful context before publication.

## Artistic covers

The opening should feel like an art exhibition poster, with intentional typography,
composition, texture, and a strong artifact or visual motif. Draw on an appropriate
art movement, historical poster genre, or contemporary design approach. Choose a
style that suits the exhibition; do not mechanically apply Egyptian imagery or
Art Deco to every civilization. Keep the actual exhibit title clear at screen distance.

Use the available imagegen skill/tool when making a new raster poster. Inspect
reference artifacts first and identify the role of each reference. Preserve the
identity of actual objects; do not imply that a modern illustration is archaeological
evidence. Keep covers landscape 16:9, with safe text margins and restrained copy.

Save the final cover to assets/<theme-slug>-cover.png. met_curator.py automatically
uses that asset for that theme. Inspect the result, install/update the runtime copy,
and verify the opening slide. Back up a current cover before replacing it. The
included old-kingdom-cover.png establishes the current quality direction.

The systemd curator timer does not run an AI agent or invoke imagegen. These are
standing instructions for agents doing exhibition work; do not claim that saving
this file schedules autonomous AI research or cover generation. If the owner asks
for scheduled agent work, configure that explicitly with an available scheduler.

## Implementation and verification

- Treat this repository as the maintained source. Do not edit only an installed copy.
- Original curator/fetcher modules live at repository root; the live viewer uses
  slideshow.py, auto_captions.py, caption_reference.py, clean_images.py, and JSON data.
- Default system install: /opt/met-screensaver. Exhibits: /srv/screensaver/exhibits;
  /srv/screensaver/current is an atomic symlink. Preserve collection history/state.
- This owner's current viewer override points to
  ~/.local/share/met-screensaver/idle_slideshow.sh. Check systemctl --user cat
  met-slideshow.service before choosing a deployment path; avoid stale overrides.
- Keep caches, local credentials, session data, history, downloads, and backups out
  of Git. Bundle only explicitly selected public assets with provenance.
- Validate offline first: Python compilation, bash -n, unit tests, then a GTK smoke
  test under Xvfb using GSK_RENDERER=cairo. Verify full-screen image allocation,
  wrapped paragraphs, reference format, cover handling, transitions, and future manifests.
- Do not run the networked curator or a dry run during ordinary development tests.
  It queries museum APIs even in dry-run mode. Publishing an exhibit should be
  deliberate and preserve the previous current exhibit if collection fails.
