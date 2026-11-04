"""Select sourced historical context, matched to the exhibit and catalog facts.

The bank is curated locally. It supplies period context, not newly researched
claims about an unseen object's maker, exact use, or provenance.
"""
import hashlib
import json
from pathlib import Path
import re

BANK = json.loads(Path(__file__).with_name('context-bank.json').read_text())
EGYPT_THEMES = {'old-kingdom','middle-kingdom','new-kingdom-amarna',
                'late-ptolemaic','egyptian-amulets'}


def clean(value):
    return ' '.join(value.split()) if isinstance(value,str) else ''


def infer_theme(metadata):
    text=' '.join(clean(metadata.get(k)).lower() for k in
                  ('culture','period','title','department'))
    for phrase,theme in (
        ('mycenaean','mycenaean'),('minoan','cycladic-minoan'),
        ('cycladic','cycladic-minoan'),('etruscan','etruscan'),
        ('cypriot','cypriot'),('phoenician','phoenician-levantine'),
        ('hittite','anatolia-hittites'),('old kingdom','old-kingdom'),
        ('middle kingdom','middle-kingdom'),('new kingdom','new-kingdom-amarna'),
        ('amarna','new-kingdom-amarna'),('ptolemaic','late-ptolemaic'),
        ('late period','late-ptolemaic'),('hellenistic','hellenistic'),
        ('geometric','geometric-archaic'),('archaic','geometric-archaic')):
        if phrase in text: return theme
    if 'roman' in clean(metadata.get('culture')).lower():
        if 'glass' in clean(metadata.get('medium')).lower(): return 'roman-luxury'
        return 'roman-portraits'
    return ''


def context_entry(metadata, theme='', record_id=''):
    if not isinstance(metadata,dict): metadata={}
    inferred=infer_theme(metadata)
    theme=theme or inferred
    facts=' '.join(clean(metadata.get(k)).lower() for k in
                   ('culture','period','title','department'))
    # An explicit culture prevents a foreign object borrowing Egyptian meanings.
    culture=clean(metadata.get('culture')).lower()
    egypt=('egypt' in culture or (not culture and
           ('egypt' in facts or theme in EGYPT_THEMES)))
    matches=[]
    for entry in BANK:
        if entry['culture']:
            if entry['culture']=='egypt':
                if not egypt: continue
            elif entry['culture'] not in facts: continue
        if entry['themes'] and theme not in entry['themes']: continue
        if entry['match']:
            field=entry['field']
            if field=='facts':
                value=facts+' '+clean(metadata.get('medium'))
            elif field=='vessel_material':
                if not re.search(r'\b(jar|bowl|vessel|vase|cup|bottle)\b',clean(metadata.get('title')),re.I):
                    continue
                value=clean(metadata.get('medium'))
            else:
                value=clean(metadata.get(field))
            if not re.search(entry['match'],value,re.I): continue
        matches.append(entry)
    # Match object-specific features before falling back to general period context.
    specific=[e for e in matches if e['match'] or e['culture']]
    candidates=specific or matches
    if candidates:
        if specific:
            return candidates[0]
        key=record_id or clean(metadata.get('title'))
        index=int(hashlib.sha256(key.encode()).hexdigest(),16)%len(candidates)
        return candidates[index]
    return dict(id='evidence',sources=[],lens='anthropology',text=(
        'An object’s historical meaning depends on who made, used, and preserved it. '
        'Without a secure cultural or archaeological context, its appearance alone cannot '
        'establish the beliefs or social position of its users.'))


def make_caption(metadata, seconds=12, theme='', record_id=''):
    text=context_entry(metadata,theme,record_id)['text']
    # Shorter display intervals use complete sentences, never a broken argument.
    budget=max(12,min(40,int(seconds*3)))
    if len(text.split())<=budget: return text
    sentences=re.split(r'(?<=[.!?])\s+',text)
    fitted=''
    for sentence in sentences:
        candidate=(fitted+' '+sentence).strip()
        if len(candidate.split())>budget: break
        fitted=candidate
    return fitted or text  # retain a complete historical idea at very short timings
