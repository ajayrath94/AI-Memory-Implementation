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


def test_companion_name_is_per_user():
    """The companion's name is never a person in the user's life — and it is
    per-user, so the same string can be a relative for one user and the
    companion for another. test_user's companion is literally named Shubham.
    """
    # NB: don't use "Arjun" as the control — test_user was renamed through
    # Arjun during development, so it lives in bot_name_history and is
    # (correctly) reserved for that user forever.
    assert merge(["Shubham", "Vikram"], [], user_id="default") == ["Shubham", "Vikram"]
    assert merge(["Shubham", "Vikram"], [], user_id="test_user") == ["Vikram"]


def test_reserved_falls_back_without_user_id():
    # No user_id (older call sites, or a failed lookup) still filters the
    # product default rather than filtering nothing.
    assert merge(["Nancy", "Arjun"], []) == ["Arjun"]
