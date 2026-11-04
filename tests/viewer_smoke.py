"""Offline integration test; no museum downloads or production display changes."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PIL import Image
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk
import clean_images
from slideshow import Show

errors=[]
checked=[]
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp)
    clean_images.CACHE=root/'cache'
    clean_images.CACHE.mkdir()
    obj={'record_id':'test:1','slide':'001.jpg','metadata':{'title':'Stirrup jar','date':'ca. 1400 BCE','culture':'Mycenaean','image_url':'https://example.invalid/original.jpg'}}
    image=Image.new('RGB',(1920,1080),'#884422')
    image.save(root/'001.jpg')
    image.save(root/'000_title.jpg')
    image.save(clean_images.cache_path(obj),'JPEG')
    (root/'exhibit.json').write_text(json.dumps({'theme':'mycenaean','objects':[obj]}))
    options=argparse.Namespace(seconds=12,fade_ms=50,images=[str(root/'001.jpg'),str(root/'000_title.jpg')])

    class Preview(Show):
        def leave(self):pass
        def do_activate(self):
            super().do_activate()
            GLib.timeout_add(1200,self.verify)
        def verify(self):
            try:
                page,pic,panel,label=self.pages[0],self.pics[0],self.panels[0],self.labels[0]
                assert pic.get_width()==page.get_width()==1920
                assert pic.get_height()==page.get_height()==1080
                assert not panel.has_css_class('loading')
                assert panel.get_halign()==Gtk.Align.START
                assert label.get_text().endswith('Stirrup jar · ca. 1400 BCE')
                assert label.get_layout().get_line_count()>=2
                self.advance()
                assert not self.panels[1].get_visible()
                checked.append(True)
            except Exception as error:errors.append(error)
            self.quit()
            return False
    Preview(options).run([sys.argv[0]])
if errors:raise errors[0]
assert checked,'Viewer exited before validation'
print('GTK smoke test passed: full-size art, combined translucent block, future caption, title card, transition')
