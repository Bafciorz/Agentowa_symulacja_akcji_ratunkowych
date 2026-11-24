"""
Moduł SAR (Search and Rescue - Poszukiwania Zaginionych):
- lost_person.py: Model zachowania zaginionego turysty (statystyki Koestera / NASAR).
- search_manager.py: Przeszukiwanie sektorów, wskaźnik Probability of Detection (PoD).
"""

try:
    from src.sar.lost_person import LostPerson
except ImportError:
    LostPerson = None

__all__ = ["LostPerson"]
