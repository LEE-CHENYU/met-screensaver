#!/usr/bin/env python3
"""Full-screen, non-interactive slideshow for the idle screensaver (GTK 4, Wayland).

Unlike an image viewer, nothing can be panned, zoomed, dragged or skipped: each image is shown whole on black with a
slow cross-fade, the cursor is hidden, and ANY key, click, scroll or real pointer movement closes the window at once.
Usage: slideshow.py --seconds 12 image1.jpg image2.jpg ...   (images are shown in the given order, then loop)"""
import argparse, sys, json
from pathlib import Path
from auto_captions import make_caption
from caption_reference import reference_for
from clean_images import BackgroundCache, cached
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=12)
    ap.add_argument("--fade-ms", type=int, default=1200)
    ap.add_argument("images", nargs="+")
    return ap.parse_args()


GRACE_S = 1.5        # ignore synthetic pointer events while the window appears
MOVE_PX = 6          # pointer must really move this far to count as input


class Show(Gtk.Application):
    def __init__(self, options):
        super().__init__(application_id="local.met-screensaver.slideshow", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.options = options
        self.index, self.ready, self.origin = 0, False, None

    def do_activate(self):
        css = Gtk.CssProvider()
        css.load_from_string("""
            window, stack, picture, box { background: #000000; }
            box.caption-panel { background: rgba(0, 0, 0, 0.32);
                padding: 12px 20px; border-radius: 8px; }
            box.caption-panel.loading { background: #101214; border-radius: 0; }
            label.reading-caption { color: #ffffff; font-size: 25px;
                text-shadow: 0 1px 3px rgba(0, 0, 0, 0.95); }
        """)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        win = Gtk.ApplicationWindow(application=self, decorated=False, title="Screensaver")
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=self.options.fade_ms)
        self.pics = [Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True, can_target=False) for _ in range(2)]
        self.pages, self.labels, self.panels = [], [], []
        self.notes = json.loads(Path(__file__).with_name("captions.json").read_text())
        self.catalogs = {}
        self.themes = {}
        self.visible_records = [None, None]
        self.clean_cache = BackgroundCache(lambda record, path:
            GLib.idle_add(self.original_ready, record.get("record_id"), str(path)))
        for i, p in enumerate(self.pics):
            page = Gtk.Overlay()
            label = Gtk.Label(wrap=True, justify=Gtk.Justification.LEFT, xalign=0,
                              hexpand=False, can_target=False)
            label.add_css_class("reading-caption")
            label.set_max_width_chars(80)
            label.set_halign(Gtk.Align.START)
            label.set_valign(Gtk.Align.CENTER)
            panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            panel.add_css_class("caption-panel")
            panel.set_valign(Gtk.Align.END)
            panel.set_halign(Gtk.Align.START)
            panel.set_margin_start(24)
            panel.set_margin_end(24)
            panel.set_margin_bottom(24)
            panel.set_vexpand(False)
            label.set_vexpand(True)
            panel.append(label)
            p.set_vexpand(True)
            p.set_hexpand(True)
            page.set_child(p)
            page.add_overlay(panel)
            page.set_measure_overlay(panel, False)
            self.panels.append(panel)
            self.pages.append(page)
            self.labels.append(label)
            self.stack.add_named(page, str(i))
        win.set_child(self.stack)
        win.set_cursor(Gdk.Cursor.new_from_name("none", None))

        keys = Gtk.EventControllerKey(); keys.connect("key-pressed", lambda *_: self.leave()); win.add_controller(keys)
        click = Gtk.GestureClick(button=0); click.connect("pressed", lambda *_: self.leave()); win.add_controller(click)
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll.connect("scroll", lambda *_: self.leave() or True); win.add_controller(scroll)
        motion = Gtk.EventControllerMotion(); motion.connect("motion", self.on_motion); win.add_controller(motion)

        self.show_image(0, first=True)
        win.fullscreen()
        win.present()
        GLib.timeout_add(int(GRACE_S * 1000), self.arm)
        GLib.timeout_add(int(self.options.seconds * 1000), self.advance)

    def arm(self):
        self.ready = True
        return False

    def on_motion(self, _ctl, x, y):
        if not self.ready:
            self.origin = (x, y)
            return
        if self.origin is None:
            self.origin = (x, y)
        elif abs(x - self.origin[0]) + abs(y - self.origin[1]) > MOVE_PX:
            self.leave()

    def show_image(self, i, first=False):
        slot = 0 if first else 1 - int(self.stack.get_visible_child_name())
        path = Path(self.options.images[i % len(self.options.images)])
        text = self.caption_for(path)
        record = self.catalogs.get(path.parent.resolve(), {}).get(path.name)
        original = cached(record) if record else None
        self.visible_records[slot] = record.get("record_id") if record else None
        self.pics[slot].set_filename(str(original or path))
        self.set_loading(slot, bool(record and not original))
        if record and not original:
            self.clean_cache.request(record)
        reference = reference_for(record, self.themes.get(path.parent.resolve(), "")) if record else ""
        markup = GLib.markup_escape_text(text)
        if reference:
            markup += '\n<span size="small" foreground="#e0e3e6">' + GLib.markup_escape_text(reference) + '</span>'
        self.labels[slot].set_markup(markup)
        self.panels[slot].set_visible(bool(text or reference))
        self.stack.set_visible_child(self.pages[slot])

    def set_loading(self, slot, loading):
        panel = self.panels[slot]
        if loading:
            # Until the original arrives, cover the old baked reference once.
            panel.add_css_class("loading")
            panel.set_halign(Gtk.Align.FILL)
            panel.set_margin_start(0)
            panel.set_margin_end(0)
            panel.set_margin_bottom(0)
            panel.set_size_request(-1, 164)
        else:
            panel.remove_css_class("loading")
            panel.set_halign(Gtk.Align.START)
            panel.set_margin_start(24)
            panel.set_margin_end(24)
            panel.set_margin_bottom(24)
            panel.set_size_request(-1, -1)

    def original_ready(self, record_id, path):
        for slot, current in enumerate(self.visible_records):
            if current == record_id:
                self.pics[slot].set_filename(path)
                self.set_loading(slot, False)
        return False

    def caption_for(self, path):
        # Resolve the catalog for each exhibit; new weekly exhibits keep working.
        directory = path.parent.resolve()
        if directory not in self.catalogs:
            try:
                data = json.loads((directory / "exhibit.json").read_text())
                self.catalogs[directory] = {o["slide"]: o for o in data.get("objects", [])}
                self.themes[directory] = data.get("theme", "")
                for image in self.options.images:
                    candidate = self.catalogs[directory].get(Path(image).name)
                    if candidate:
                        self.clean_cache.request(candidate)
            except (OSError, ValueError, KeyError, TypeError):
                self.catalogs[directory] = {}
        record = self.catalogs[directory].get(path.name)
        if not record:
            return ""
        if record.get("record_id") in self.notes:
            return self.notes[record["record_id"]]
        # Generate a reading caption for every new exhibit, automatically.
        # Explicit per-object captions in a future manifest may override this.
        editorial = record.get("caption")
        if isinstance(editorial, str) and editorial.strip():
            return editorial.strip()
        return make_caption(record.get("metadata", {}), self.options.seconds,
                            self.themes.get(directory, ""), record.get("record_id", ""))

    def advance(self):
        self.index += 1
        self.show_image(self.index)
        return True

    def leave(self):
        self.quit()


if __name__ == "__main__":
    sys.exit(Show(parse_args()).run([sys.argv[0]]))
