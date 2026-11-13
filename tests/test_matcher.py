"""Matcher regression tests. Every miss in the miss log becomes a case here.
Run:  python3 -m pytest -q tests   (or python3 tests/test_matcher.py)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scanner.matcher import match, norm  # noqa: E402

MUST_MATCH = [
    # miss_log: BRGM Guadeloupe 9 Nov 2026 ("héliportés" vs "aéroportés")
    "Réalisation d'une campagne en gamma-spectrométrie et magnétisme héliportés en Guadeloupe",
    # miss_log: Petrobras Pelotas data licence 13 Nov 2026
    "Aquisição de licença de uso de dados geofísicos aerolevantados da Bacia de Pelotas",
    "Aerolevantamento magnetométrico e gamaespectrométrico",
    "Levantamento aerogeofísico na Província Mineral do Tapajós",          # SGB wording
    "Levés aéromagnétiques et spectrométriques de la zone nord",
    "Aerogeophysical data acquisition services",
    "Airborne magnetic and radiometric survey, Blocks 10 and 12",
    "Fixed-wing aeromagnetic gradiometer survey",
    "Helicopter-borne time-domain electromagnetic (TDEM) survey",
    "Heliborne TEM survey over the Kibali belt",
    "Airborne gravity gradiometry (FTG) acquisition",
    "Upphandling av flygtjänster för geofysiska flygmätningar och strålskydd",  # SGU, TED 757232-2026
    "Аэрогеофизическая съёмка масштаба 1:50 000",
    "Αερομαγνητική χαρτογράφηση",
    "Survei geofisika udara aeromagnetik",
    "Levantamiento geofísico aéreo de magnetometría y espectrometría gamma",
    "Khảo sát địa vật lý hàng không",                                       # Vietnamese đ fold
    "항공물리탐사 용역",
    "Havadan jeofizik etüt hizmeti",
    "Aerogeophysikalische Befliegung Harz",
    "Providers to carry out multi-sensor aero-geophysical surveys (magnetic gradiometer and radiometric)",  # GSI, FirstTender
    "Kontrakt vedr. luftbåren geofysisk dataindsamling",                 # Miljøstyrelsen, udbud 00752814-2026
]

MUST_NOT_MATCH = [
    "Aerial survey of forest fires",
    "System maintenance and demand management services",   # 'tem'/'dem' inside words
    "Transports sanitaires héliportés région PACA",         # helicopter ambulance
    "Schaumlöschanlage mit dem Hubschrauber-Landeplatz",    # German article 'dem'
    "Programa de capacitação em gestão pública",            # 'gama' inside 'programa'
    "Supply of MRI magnetic resonance scanner",
    "Aerial photography and orthophoto production 2027",
]


def test_must_match():
    missed = [t for t in MUST_MATCH if not match(t)]
    assert not missed, f"matcher missed: {missed}"


def test_must_not_match():
    wrong = [(t, match(t)["terms"]) for t in MUST_NOT_MATCH if match(t) and match(t)["score"] >= 2]
    assert not wrong, f"false positives (score>=2): {wrong}"


def test_drone_flag():
    m = match("Levantamento aeromagnético com drone (VANT)")
    assert m and m["drone_only"]
    m = match("Airborne magnetic survey by helicopter and drone")
    assert m and not m["drone_only"]


def test_norm_folds():
    assert "magnetometrico" in norm("Magnetométrico")
    assert "dia vat ly" in norm("Địa vật lý")
    assert norm("") == ""


if __name__ == "__main__":
    for f in (test_must_match, test_must_not_match, test_drone_flag, test_norm_folds):
        try:
            f(); print("PASS", f.__name__)
        except AssertionError as e:
            print("FAIL", f.__name__, e)
