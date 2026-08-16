"""Regression cases for profile list canonicalisation.

Every case here is one that broke at some point during development — the
cleaners subtract noise, and each new subtraction rule created a way for
debris to survive as a fake entity. Add a case whenever one gets through.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from memory.profile_store import _canonical_key as key, _merge_list as merge

DROP = ""

def test_hedges_and_fragments():
    assert key("in Bangalore") == DROP            # location fragment, no name
    assert key("mentioned but location unknown") == DROP   # hedge debris
    assert key("possibly chronic") == DROP
    assert key("son (location unknown to user)") == DROP   # bare relation word
    assert key("Beta (son/child)") == DROP                 # hinglish relation
    assert key("Daughter - Living abroad") == DROP

def test_variants_collapse():
    assert key("Arjun (doctor, Delhi)") == "arjun"
    assert key("Son: Arjun - Doctor in Delhi") == "arjun"  # leading label
    assert key("Arjun in Mumbai") == "arjun"               # trailing PP
    assert key("Shubham (son, lives in Bangalore)") == "shubham"

def test_real_names_survive():
    assert key("Meena (daughter, lives abroad)") == "meena"
    assert key("Arjun") == "arjun"

def test_reserved():
    # Nancy is the companion; the owner is not her own relative.
    assert merge(["Nancy (appears to be a caregiver)", "Shubham"],
                 [], owner="Shobha") == ["Shubham"]
    assert merge(["Shobha (mentioned as someone speaking)", "Arjun"],
                 [], owner="Shobha") == ["Arjun"]

def test_dict_entries_not_dropped():
    assert merge([{"name": "Arjun", "occupation": "doctor"}, "Arjun in Mumbai"],
                 [], owner="Kamala") == ["Arjun"]

def test_module_imports_cleanly():
    import memory.profile_store  # noqa: F401
