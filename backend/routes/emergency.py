"""
EMERGENCY ROUTE

One GET. Everything it returns is already known — her caregivers with their
numbers, the two national ones, and whatever hospital is nearest to where the
phone last reported being.

Nothing here decides when to show it. The screen is somewhere she goes, not
something that arrives: a card appearing unbidden saying "here are emergency
numbers" frames an ordinary trip as dangerous, and she is likelier to worry
than to feel looked after.
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/{user_id}")
def emergency_card(user_id: str):
    """Her people, the national numbers, and the nearest hospital.

    Ordered as she would want it: a son who knows her history is more use in
    the first minute than any hospital switchboard.
    """
    from memory.emergency import card
    try:
        return card(user_id)
    except Exception as e:
        print(f"[Emergency] card failed: {e}")
        # Never empty. The two national numbers are constants and reach
        # everything in India, so even a total failure of everything else
        # leaves her with something to dial.
        return {
            "entries": [
                {"label": "Ambulance", "number": "108", "kind": "national"},
                {"label": "Emergency", "number": "112", "kind": "national"},
            ],
            "where": "",
            "degraded": True,
        }
