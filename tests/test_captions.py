import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from auto_captions import BANK, context_entry, make_caption
from caption_reference import reference_for
import met_curator


class Captions(unittest.TestCase):
    def test_all_exhibition_themes_have_sourced_context(self):
        for theme in met_curator.THEMES:
            with self.subTest(theme=theme.slug):
                entry=context_entry({'title':'New catalog object'},theme.slug,'sample:1')
                self.assertTrue(entry['sources'])
                self.assertLessEqual(len(make_caption({},theme=theme.slug).split()),36)

    def test_context_respects_culture_and_material(self):
        self.assertEqual(context_entry({'title':'Hand amulet','culture':'Egypt'},'old-kingdom')['id'],'egypt-limbs')
        self.assertTrue(context_entry({'title':'Hand amulet','culture':'Etruscan'},'etruscan')['id'].startswith('etruscan'))
        self.assertEqual(context_entry({'title':'Bowl','culture':'Egypt','medium':'Travertine'},'old-kingdom')['id'],'egypt-stone')
        self.assertNotEqual(context_entry({'title':'Statue','culture':'Egypt','medium':'Limestone'},'old-kingdom')['id'],'egypt-stone')

    def test_context_respects_chronology(self):
        self.assertEqual(context_entry({'period':'Late Period'},'late-ptolemaic')['id'],'late-period-context')
        self.assertEqual(context_entry({'period':'Archaic'},'geometric-archaic')['id'],'archaic-context')
        self.assertNotEqual(context_entry({'culture':'Anatolian','period':'Early Bronze Age'},'anatolia-hittites')['id'],'hittite-context')

    def test_editorial_coverage_and_provenance(self):
        catalog=json.loads((ROOT/'examples/old-kingdom/exhibit.json').read_text())
        notes=json.loads((ROOT/'captions.json').read_text())
        sources=json.loads((ROOT/'caption-sources.json').read_text())
        for obj in catalog['objects']:
            key=obj['record_id']
            self.assertIn(key,notes)
            self.assertTrue(sources[key]['sources'])
            self.assertLessEqual(len(notes[key].split()),36)

    def test_visible_reference_is_compact(self):
        obj={'record_id':'new:1','metadata':{'title':'Bowl','date':'ca. 2400 BCE','culture':'Egypt','page_url':'https://example.org/','credit':'A museum'}}
        self.assertEqual(reference_for(obj,'old-kingdom'),'Bowl · ca. 2400 BCE')
        obj={'record_id':'commons:55269374','metadata':{'title':'Lintel of Hesy, Koptos, Egypt, The Petrie Museum'}}
        self.assertEqual(reference_for(obj,'old-kingdom'),'Lintel of Hesy · Old Kingdom')

    def test_custom_cover_is_used(self):
        from datetime import date
        theme=next(t for t in met_curator.THEMES if t.slug=='old-kingdom')
        cover=met_curator.render_title_card(theme,[],date.today())
        self.assertEqual(cover.size,(1920,1080))
        self.assertGreater(cover.getpixel((50,50))[0],100)


if __name__=='__main__':unittest.main()
