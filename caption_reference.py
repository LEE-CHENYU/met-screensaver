"""Compact object identification for the screensaver caption block."""
import re

TITLES = {
 'commons:101199220': 'Relief from Sahure’s mortuary temple',
 'commons:101200051': 'Funerary statue',
 'commons:101200057': 'Stone funerary statue',
 'commons:12168301': 'The Great Pyramid',
 'commons:17413802': 'Nobleman and his wife',
 'commons:179499096': 'False door',
 'commons:27697126': 'Tomb relief of Iny',
 'commons:51754049': 'Pyramids',
 'commons:55269374': 'Lintel of Hesy',
 'commons:64130474': 'Pyramids',
 'commons:65344483': 'Bowl',
 'commons:77265314': 'Striding statue of Minnefer',
 'commons:93050616': 'Beer jar',
 'commons:9580179': 'Pyramid complex',
 'commons:9979971': 'Royal genealogy',
}
PERIODS = {
 'old-kingdom':'Old Kingdom', 'middle-kingdom':'Middle Kingdom',
 'new-kingdom-amarna':'New Kingdom', 'late-ptolemaic':'Late Period–Ptolemaic Period',
 'cycladic-minoan':'Bronze Age Aegean', 'mycenaean':'Mycenaean period',
 'geometric-archaic':'Geometric–Archaic period', 'athenian-vases':'Archaic–Classical period',
 'classical-sculpture':'Classical period', 'hellenistic':'Hellenistic period',
 'roman-portraits':'Roman period', 'roman-luxury':'Roman period',
}

def clean(value):
 return ' '.join(value.split()) if isinstance(value,str) else ''


def reference_for(record, theme=''):
 metadata=record.get('metadata',{})
 title=TITLES.get(record.get('record_id')) or clean(metadata.get('title')) or 'Untitled'
 title=re.sub(r'\s*\(\d{6,}\)', '',title)
 title=re.split(r'\s+-\s+|\s+DSC\d+', title)[0]
 # Photo filenames can contain long collection/location tails; keep identification brief.
 if len(title.split())>14:
  title=re.split(r',|;|\s+from\s+',title,maxsplit=1,flags=re.I)[0]
 if len(title.split())>14:
  title=' '.join(title.split()[:14]).rstrip(' ,;')+'…'
 period=clean(metadata.get('date')) or clean(metadata.get('period')) or PERIODS.get(theme,'')
 return title + (' · '+period if period else '')
