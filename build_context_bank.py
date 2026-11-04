"""Maintain researched context paragraphs and their sources (no network calls)."""
import json
from pathlib import Path
P=Path(__file__).parent
M='https://www.metmuseum.org/essays/'
sources={
 'old':M+'egypt-in-the-old-kingdom-ca-2649-2150-b-c',
 'giza':'https://giza.fas.harvard.edu/faq/',
 'workers':'https://aeraweb.org/projects/lost-city/',
 'amulets':M+'egyptian-amulets',
 'hands':'https://www.metmuseum.org/art/collection/search/548367',
 'faience':M+'egyptian-faience-technology-and-production',
 'stone':'https://www.ucl.ac.uk/museums-static/digitalegypt/stone/vessels.html',
 'seal':'https://archiv.ub.uni-heidelberg.de/propylaeumdok/4188/1/Bussmann_Seal_and_seal_2011.pdf',
 'false':'https://www.metmuseum.org/art/collection/search/577370',
 'offer':'https://www.metmuseum.org/art/collection/search/577372',
 'minnefer':'https://www.clevelandart.org/art/1948.420',
 'captive':'https://www.metmuseum.org/art/collection/search/543869',
 'farming':'https://www.clevelandart.org/art/1930.735',
 'middle':M+'egypt-in-the-middle-kingdom-2030-1640-b-c',
 'new':M+'egypt-in-the-new-kingdom-ca-1550-1070-b-c',
 'ptolemy':'https://www.metmuseum.org/perspectives/egyptian-ptolemaic-art-installation',
 'cycladic':M+'early-cycladic-art-and-culture',
 'minoan':M+'minoan-crete',
 'mycenaean':M+'mycenaean-civilization',
 'geometric':M+'geometric-art-in-ancient-greece',
 'vases':'https://resources.metmuseum.org/resources/metpublications/pdf/Greek_Art_From_Prehistoric_to_Classical.pdf',
 'classical':M+'the-art-of-classical-greece-ca-480-323-b-c',
 'hellenistic':M+'art-of-the-hellenistic-age-and-the-hellenistic-tradition',
 'etruscan':M+'etruscan-art',
 'cypriot':'https://www.metmuseum.org/exhibitions/listings/2014/assyria-to-iberia',
 'phoenician':M+'the-phoenicians-1500-300-b-c',
 'roman':M+'roman-portrait-sculpture-the-stylistic-cycle',
 'glass':M+'roman-glass',
 'hittite':M+'the-hittites',
 'late':M+'egypt-in-the-late-period-ca-712-332-b-c',
 'archaic':M+'greek-art-in-the-archaic-period',
 'paint':'https://oyc.yale.edu/history-art/hsar-252/lecture-8',
 'anatolia':'https://www.metmuseum.org/exhibitions/listings/2003/art-of-the-first-cities',
}
bank=[]
def add(id,text,source,*,themes=(),culture='',match='',field='title',lens='society'):
 bank.append(dict(id=id,text=text,sources=[sources[source]],themes=list(themes),culture=culture,match=match,field=field,lens=lens))
# Specific contexts take priority over broader exhibit introductions.
add('egypt-limbs','Egyptian limb amulets were believed to protect corresponding body parts and perhaps strengthen their abilities. Material and color mattered too: blood-like carnelian could express vitality within this system of personal protection.','hands',culture='egypt',match=r'\b(hand|foot|leg)\b.*amulet|amulet.*\b(hand|foot|leg)\b',lens='anthropology')
add('egypt-amulets','Egyptians wore amulets to obtain protection and well-being. Shape, material, color, and ritual action could give an object power, linking personal adornment to a practical religious response to bodily vulnerability.','amulets',culture='egypt',match=r'amulet|wedjat|scarab',lens='belief')
add('egypt-faience','Egyptian faience combined crushed quartz with ingredients that formed a glassy surface during firing. This manufactured brilliance carried associations of life and renewal, joining controlled material transformation to religious meaning.','faience',culture='egypt',match=r'faience',field='medium',lens='technology')
add('egypt-false-door','Egyptian false doors provided a ritual meeting place between living and dead. Offerings deposited in front sustained the deceased, making commemoration an ongoing relationship maintained through food, prayers, and family participation.','false',culture='egypt',match=r'false door',lens='anthropology')
add('egypt-captives','Old Kingdom captive statues placed defeated foreigners within royal pyramid complexes. Their bodies expressed subjugation, turning sculpture into a political and ritual assertion that the king could dominate forces beyond Egypt.','captive',themes=['old-kingdom'],culture='egypt',match=r'captive',lens='power')
add('egypt-offerings','In Egyptian tombs, images and lists of offerings could sustain the deceased even when actual deliveries ceased. Religious expectations turned food, material provision, and remembrance into obligations extending beyond death.','offer',culture='egypt',match=r'offering|butcher',lens='economics')
add('egypt-agrarian','Old Kingdom tomb scenes connected farming, animal resources, and food deliveries to an official’s continued existence. They preserve evidence of work, but through images selected to provision and commemorate an elite owner.','farming',themes=['old-kingdom'],culture='egypt',match=r'agricultur|harvest|cattle|birds|desert animals',lens='economics')
add('egypt-stone','Egyptian stone vessels were hollowed using drilling tools after their exterior was shaped. A finished container embodied specialist knowledge and patient labor, connecting ordinary household forms to a highly developed technical tradition.','stone',culture='egypt',match=r'\b(travertine|alabaster|gneiss|limestone|basalt|stone)\b',field='vessel_material',lens='technology')
add('egypt-seal','Egyptian seals and their clay impressions help reconstruct the administration behind royal power. Repeatable carved marks connected individuals and offices to procedures for controlling goods, extending authority into everyday material transactions.','seal',culture='egypt',match=r'\bseal\b',lens='administration')
add('egypt-tomb-statue','Egyptian tomb statues could become substitutes for the deceased after ritual activation. Receiving offerings through an image linked beliefs about personal survival to specialist craftsmanship and continuing nourishment supplied by the living.','minnefer',culture='egypt',match=r'funerary statue|tomb statue|ka.statue',lens='belief')
add('roman-glass','Roman glass production expanded rapidly after glassblowing developed in the eastern Mediterranean. Faster manufacture widened the range of vessel forms, connecting workshop innovation and mobile craft knowledge to changing patterns of consumption.','glass',culture='roman',match='glass',field='medium',lens='technology')
add('minoan-context','Minoan palaces concentrated political authority, workshops, and agricultural resources. Administrative writing accompanied these institutions, linking finely made objects to systems for organizing production and managing goods as well as to ritual life.','minoan',culture='minoan',lens='economics')
add('cycladic-context','Early Cycladic communities combined maritime exchange with rich island mineral resources. Unequal quantities of burial goods suggest differences in wealth, so objects illuminate both regional connections and emerging distinctions within island societies.','cycladic',culture='cycladic',lens='society')
add('late-period-context','Egypt’s Late Period combined renewed use of older artistic traditions with changing foreign pressures. Saite rulers reunified the country, while later Persian conquest altered sovereignty without ending the importance of established Egyptian religious practices.','late',themes=['late-ptolemaic'],match=r'late period|saite|dynasty 26|dynasty 27',field='facts',lens='history')
add('archaic-context','Archaic Greek artists adapted ideas arriving through contact with Egypt and the Near East. New forms of monumental sculpture and painted pottery reveal cultural exchange as local workshops developed distinctive ways to represent bodies and stories.','archaic',themes=['geometric-archaic'],match=r'archaic',field='facts',lens='exchange')
add('roman-painting','Roman wall paintings brought myth, landscapes, everyday scenes, and imagined architecture into domestic spaces. The choice of subjects made the household a setting for engaging with stories and places beyond its physical walls.','paint',themes=['roman-luxury'],match=r'fresco|paint',field='facts',lens='culture')
add('hittite-context','The Hittite kingdom ruled from fortified Hattusha and competed with major neighboring powers. Warfare, diplomacy, and royal marriage linked Anatolia to Syria and Egypt, placing courtly objects within international political relationships.','hittite',themes=['anatolia-hittites'],match=r'hittite',field='facts',lens='power')
# Two paragraphs per theme allow stable variation across future object slides.
contexts={
'cycladic-minoan':('cycladic',[
 'The early Aegean was a connected maritime region. Cycladic islanders traded mineral resources and made marble vessels and figures, while differences in burial goods suggest unequal access to material wealth.',
 'Cycladic burial goods provide much of our evidence for early island life. Because few settlements are known, surviving art offers an uneven view shaped strongly by what communities placed with their dead.']),
'mycenaean':('mycenaean',[
 'Mycenaean wealth centered on fortified palaces and powerful elites. Workshops made practical goods and luxuries, while scribes used Linear B to record an early form of Greek within palace administration.',
 'Mycenaean vessels traveled widely across the Mediterranean. Oil, wine, and other contents were probably central to this exchange, reminding us that surviving containers often record an economy built around perishable goods.']),
'geometric-archaic':('geometric',[
 'Early Greek communities developed city-states, alphabetic writing, and overseas connections. Elite displays of wealth and references to heroic stories helped establish status within societies undergoing major political and cultural change.',
 'In Geometric Greece, emerging aristocracies distinguished themselves through material wealth and heroic imagery. Objects therefore help explain how communities represented status while new civic and religious institutions were taking shape.']),
'athenian-vases':('vases',[
 'Athenian black and red pottery colors depended on controlled kiln atmospheres rather than separate paints. Skilled firing transformed clay surfaces, connecting familiar mythological scenes to demanding technical knowledge in specialist workshops.',
 'Athenian painted pottery circulated beyond Greek communities, including to wealthy Etruscan buyers. These vessels connect local workshops and shared heroic stories to overseas demand and the movement of goods across cultural boundaries.']),
'classical-sculpture':('classical',[
 'Classical Greek sculpture developed amid civic building projects and religious patronage. Public monuments made artistic skill part of communal identity, connecting representations of the human body to the institutions commissioning them.',
 'Classical Athens invested heavily in rebuilding its sacred monuments. Artistic production belonged to a civic and religious project, showing how workshops and public resources could give a city’s identity a durable form.']),
'hellenistic':('hellenistic',[
 'After Alexander’s conquests, Greek-speaking kingdoms connected communities across a greatly enlarged world. Royal patronage and the movement of artists supported new forms of display, linking artistic production to competitive centers of power.',
 'Hellenistic rulers used courts and cities as centers of artistic patronage. Expanding audiences encouraged varied subjects and forms, while the circulation of artists connected local workshops to a wider world of wealthy patrons.']),
'etruscan':('etruscan',[
 'Etruscan workshops adapted Greek and Levantine forms to local tastes. Mediterranean trade supplied materials such as ivory and amber, connecting elite consumption in Italy to distant sources and the skills of specialized craftspeople.',
 'Much Etruscan writing survives only as short texts, making art and archaeology especially important historical evidence. Tombs preserve valuable information, though their rich contents disproportionately reflect people able to afford elaborate commemoration.']),
'cypriot':('cypriot',[
 'Cyprus’s copper deposits made the island important to eastern Mediterranean powers and traders. Its location also connected routes westward, placing local craft traditions within networks of resources, exchange, and competing political interests.',
 'Ancient Cyprus stood along routes linking the Levant and the wider Mediterranean. Its copper resources attracted outside interests, showing how an island’s geology and position could shape economic connections and political relationships.']),
'phoenician-levantine':('phoenician',[
 'Phoenician cities were independent rivals connected by maritime commerce. Skilled workshops produced sought-after luxuries, linking coastal urban economies to far-reaching trade rather than to a single unified territorial state.',
 'Levantine craftspeople worked ivory, metals, timber, and textiles for markets beyond their cities. Such production connected technical expertise and prized materials to the maritime networks through which elite goods and styles circulated.']),
'roman-portraits':('roman',[
 'Roman portraits communicated political ideals as well as likeness. Rulers selected youthful, aged, or deliberately traditional appearances, making the fashioned face a way to claim authority and connect a reign to respected predecessors.',
 'Imperial Roman portrait styles helped define the image of a reign. Changes in hair, expression, and idealization could communicate continuity or difference, revealing how political authority was constructed through repeated visual choices.']),
'roman-luxury':('paint',[
 'Roman domestic paintings included myths, landscapes, ordinary activities, and imagined architecture. Household decoration connected private rooms to a wider cultural world, making stories and representations of distant places part of everyday surroundings.',
 'Painted scenes brought a range of subjects into Roman interiors, from mythological stories to everyday activities. Their variety provides evidence of the visual culture people selected to live with in domestic space.']),
'old-kingdom':('old',[
 'Old Kingdom monuments joined royal power to religious ideas about eternal life. Tomb chapels, statues, and offering scenes created settings where the living could continue to support and commemorate the dead.',
 'Old Kingdom funerary art promised nourishment and continued existence through images and ritual. Its lasting record reflects those able to commission monuments, so it reveals elite priorities more readily than the full range of Egyptian lives.']),
'middle-kingdom':('middle',[
 'Egypt’s Middle Kingdom followed political reunification under Mentuhotep II. Artists reworked older traditions as kingship, society, and afterlife beliefs changed, showing how cultural continuity could coexist with new institutions and forms of expression.',
 'Middle Kingdom culture revived and transformed inherited Egyptian traditions. Changes across sculpture, jewelry, stelae, and literature reveal a society reshaping ideas of authority and individual identity after an era of political division.']),
'new-kingdom-amarna':('new',[
 'New Kingdom Egypt expanded its political reach while kings invested in temples and richly decorated burials. Artistic production connected royal authority and religious practice to the resources mobilized by an imperial state.',
 'New Kingdom rulers separated their great mortuary temples from tombs cut into the Theban hills. Religious texts and images organized burial spaces around the deceased king’s journey and continued existence after death.']),
'late-ptolemaic':('ptolemy',[
 'In Ptolemaic Egypt, Greek rulers presented themselves both as Hellenistic monarchs and Egyptian pharaohs. Temples sustained established cults, while Greek status and new cultural connections reshaped relationships within an unequal society.',
 'Ptolemaic rulers supported Egyptian temples while living in the heavily Greek city of Alexandria. Different artistic traditions expressed authority for different settings and audiences, revealing cultural interaction without erasing distinctions of status.']),
'egyptian-amulets':('amulets',[
 'Egyptian amulets were often affordable objects of personal protection. Their power could depend on shape, material, color, and ritual action, placing religious practice close to everyday concerns about bodily safety and well-being.',
 'Egyptians placed protective objects on the living and the dead. Adornment and ritual overlapped: miniature forms were believed to transfer beneficial powers, making jewelry part of an active relationship between bodies and sacred forces.']),
 'anatolia-hittites':('anatolia',[
 'Ancient Anatolia belonged to a wider Near Eastern world connected by the movement of materials, objects, and ideas. Craft traditions provide evidence for these relationships across communities with different political and cultural histories.',
 'Objects from Anatolia belong to varied societies across many centuries. Their materials and forms help trace connections with neighboring regions, reminding us that this exhibition spans changing communities rather than a single timeless culture.']),
}
for theme,(source,texts) in contexts.items():
 for i,text in enumerate(texts): add(theme+'-'+str(i),text,source,themes=[theme])
(P/'context-bank.json').write_text(json.dumps(bank,ensure_ascii=False,indent=2)+'\n')
(P/'context-sources.json').write_text(json.dumps(sources,indent=2)+'\n')
print('Built',len(bank),'sourced historical context paragraphs for',len(contexts),'themes')
