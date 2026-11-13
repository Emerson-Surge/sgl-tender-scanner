"""Concept matcher for airborne-geophysics tenders.

Design rules (lessons from the other pipeline's miss log):
  * Accent folding happens in norm(), so every term is written ONCE, unaccented.
  * Short ambiguous terms (tem, dem, eм) are whole-word only.
  * Stems cover compounds: "aeromagnet" catches aeromagnetic / aeromagnétique /
    aeromagnetometria / aeromagnetik; "aerogeofis" catches aerogeofísico etc.
  * A term that normalises to "" can never match.
  * The matcher reports WHY it matched (tier + terms), so a reviewer can judge
    a near-miss in seconds. Recall first: verification is the precision filter.
"""
from __future__ import annotations

import re
import unicodedata

# Letters NFKD does not decompose.
_EXTRA_FOLD = str.maketrans({
    "đ": "d", "Đ": "d", "ø": "o", "Ø": "o", "æ": "ae", "Æ": "ae", "ß": "ss",
    "ł": "l", "Ł": "l", "ı": "i", "œ": "oe", "þ": "th", "ð": "d", "ё": "е",
})


def norm(text: str | None) -> str:
    if not text:
        return ""
    t = text.translate(_EXTRA_FOLD)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"[^\w]+", " ", t)  # \w is Unicode-aware: keeps Cyrillic, Arabic, CJK, Thai
    return f" {t.strip()} "


def _prep(terms):
    out = []
    for raw in terms:
        whole = raw.startswith("=")
        n = norm(raw.lstrip("=")).strip()
        if not n:
            continue
        out.append((raw.lstrip("="), f" {n} " if whole else n))
    return out


# Tier 1: strong terms, match alone. "=" prefix = whole word only.
STRONG = _prep([
    # English
    "magnetometr", "aeromagnet", "aero magnetic", "aerogeophys", "aero geophys", "aero gravi", "aero radiometr", "aerogravi", "aeroradiometr",
    "gamma ray spectrometr", "gamma spectrometr", "radiometric survey", "radiometrics",
    "electromagnetic survey", "airborne gravity", "airgrav", "gravity gradiometr",
    "=tem survey", "=tdem", "=fdem", "=vtem", "=ftg",
    "geophysical survey", "geophysical data acquisition", "geophysical mapping",
    "geophysical data processing", "processing of geophysical", "interpretation of geophysical", "geophysical data interpretation",
    "traitement des donnees geophysiques", "interpretation des donnees geophysiques", "processamento de dados geofisicos",
    "procesamiento de datos geofisicos", "reprocessing of airborne",
    # French
    "magnetometrie", "spectrometrie gamma", "gamma spectrometrie", "radiometrie",
    "leve geophysique", "leves geophysiques", "levé geophysique",
    "aeroporte geophys", "geophysique aeroportee",
    # Spanish / Portuguese
    "magnetometria", "magnetometrico", "espectrometria gama", "espectrometria gamma",
    "gamaespectr", "gamaespectrometr", "aerolevantament", "aerogeofis", "aerogravim",
    "levantamiento geofisico", "levantamento geofisico", "radiometria", "radiometrico",
    "prospeccion geofisica", "prospeccao geofisica",
    # German / Dutch / Nordic / Finnish / Polish / Turkish / Italian
    "aeromagnetik", "aerogeophysik", "geophysikalische befliegung", "hubschraubergeophysik",
    "flymagnet", "helikoptermaling", "aerogeofysi", "lentomittau", "geofysiikka", "luftbaren geofysisk", "luftbarne geofysisk", "geofysisk dataindsamling", "luftburen geofysik", "geofysisk flygmat", "geofysiska flygmat", "geofysisk malinger",
    "zdjecia geofizyczne", "geofizyki lotnicz", "aerogeofizy", "havadan jeofizik", "aeromanyetik",
    "jeofizik etut", "aerogeofisic", "rilievo geofisico",
    # Russian / Kazakh / Mongolian (Cyrillic)
    "аэрогеофизическ", "аэромагнитн", "аэрогамма", "гамма спектрометр", "электроразведк",
    "геофизическ съемк", "геофизических работ", "агаарын геофизик", "магниторазведк",
    # Greek
    "γεωφυσικ", "μαγνητομετρ", "αερομαγνητικ", "ηλεκτρομαγνητικ",
    # Arabic
    "الجيوفيزيائي", "المغناطيسية", "أشعة غاما", "المسح الجيوفيزيائي",
    # Asian languages
    "항공물리탐사", "항공자력", "항공탐사", "물리탐사", "空中物理探査", "空中磁気", "物理探査",
    "航空物探", "航磁", "khao sat dia vat ly", "dia vat ly may bay",
    "ธรณีฟิสิกส์", "survei geofisika", "geofisika udara", "aeromagnetik",
])

AIRBORNE = _prep([
    "airborne", "aerial", "helicopter", "heli borne", "fixed wing", "aircraft", "flown",
    "aeroporte", "heliporte", "aerien", "aerotransportado", "aereo", "aerotransportad",
    "aerolevantament", "helicoptero", "avion", "luftgestutzt", "hubschrauber", "befliegung",
    "flybaren", "luftbar", "luftburen", "helikopter", "lotnicz", "havadan", "elitrasportat",
    "воздушн", "аэро", "вертолет", "αερομεταφερ", "الجوي", "جوي", "udara", "agaaryn", "агаарын",
    "항공", "空中", "航空", "hang khong", "ทางอากาศ",
])

GEOPHYS = _prep([
    "geophys", "geofis", "geofys", "geofiz", "jeofizik", "magnetic", "magnet", "gamma", "=gama",
    "radiometr", "electromagnet", "eletromagnet", "gravity", "gravim", "=tem",
    "lidar", "digital elevation model", "modelo digital de elevac", "геофизич", "магнитн", "гравиметр", "γεωφυσ", "μαγνητ", "جيوفيزي", "مغناطيس",
    "물리탐사", "物理探査", "物探", "dia vat ly", "ธรณีฟิสิกส์",
])

LICENCE = _prep([
    "licenca de uso", "aquisicao de licenca", "licenciamento de uso", "licenca nao exclusiva",
    "license to use data", "licence to use data", "data licensing", "data license", "data licence",
    "non exclusive data", "licensing of data", "multiclient", "multi client",
])

# Signals that a notice is drone/UAV-only (excluded by SGL scope rule) or not survey services.
DRONE = _prep(["drone", "=uav", "=uas", "=rpas", "unmanned aerial", "dron", "vant", "беспилот", "무인기", "ドローン"])
MANNED = _prep(["helicopter", "fixed wing", "aircraft", "heliporte", "helicoptero", "вертолет", "avion"])
NEGATIVE_HINT = _prep([
    "forest fire", "incendio", "aerial photograph", "orthophoto", "ortofoto", "seismic",
    "sismic", "сейсм", "magnetic resonance", "mri", "magnetic stirrer", "electromagnetic compatib",
    "magnetic card", "magnetic tape", "gamma camera", "gamma knife", "radiotherapy",
    "ilmakuva", "hpge", "germanium", "detector", "well logging", "logging", "piezometer", "borehole", "vibrating sample",
    "wind farm", "offshore wind", "geotechnical", "explosive", "software", "measuring device", "contamination", "quantum",
    "laboratory", "laborator", "sondaj", "pozo", "poco", "skvazhin", "скважин", "aerial imagery", "aerial photo", "luchtfoto", "flygfoto", "ambulance", "sanitaire",
])


_AIR_RE = re.compile(r"aero|air|heli|flyg|flug|luftb|befliegung|flymagnet|lento|lotnicz|havadan|аэро|агаар|αερο|항공|空中|航空|udara|hang khong|=ftg|vtem|tdem|fdem|tem survey|gradiometr")


def _hits(nt: str, terms):
    return [raw for raw, n in terms if n in nt]


def match(title: str, description: str = "") -> dict | None:
    """Return a match dict or None. Tiers: strong, combo, licence."""
    nt = norm(f"{title} {description}")
    strong = _hits(nt, STRONG)
    air = _hits(nt, AIRBORNE)
    geo = _hits(nt, GEOPHYS)
    lic = _hits(nt, LICENCE)
    tier = None
    if strong:
        tier = "strong"
    elif air and geo:
        tier = "combo"
    elif lic and geo:
        tier = "licence"
    if not tier:
        return None
    drone_only = bool(_hits(nt, DRONE)) and not _hits(nt, MANNED)
    neg = _hits(nt, NEGATIVE_HINT)
    # Confidence for sorting the report: strong > combo > licence; title hits beat description hits.
    in_title = bool(_hits(norm(title), STRONG) or (_hits(norm(title), AIRBORNE) and _hits(norm(title), GEOPHYS)))
    score = {"strong": 3, "combo": 2, "licence": 1}[tier] + (1 if in_title else 0) - (1 if neg else 0)
    airborne = bool(air) or any(_AIR_RE.search(t) for t in strong)
    return {
        "tier": tier,
        "airborne": airborne,
        "terms": sorted(set(strong or (air + geo) or (lic + geo)))[:8],
        "drone_only": drone_only,
        "negative_hints": neg,
        "in_title": in_title,
        "score": score,
    }
