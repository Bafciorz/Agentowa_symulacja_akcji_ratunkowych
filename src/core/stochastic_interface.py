"""
Interfejsy i klasy abstrakcyjne dla stochastycznego generatora zdarzeń GOPR.

Wzorzec Strategii (Strategy Pattern) rozdzielający generowanie zgłoszenia na 3 niezależne wymiary:
1. AbstractArrivalProcess - oś czasu (kiedy następuje wezwanie?)
2. AbstractIncidentTypeSampler - oś medyczna/triage (co się stało i ilu ratowników potrzeba?)
3. AbstractSpatialSampler - oś przestrzenna (gdzie na mapie doszło do wypadku?)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Callable, Optional, Union
import numpy as np

from src.core.incident import Priority


# ==============================================================================
# SPECYFIKACJA TYPU ZDARZENIA (INCIDENT TYPE SPECIFICATION)
# ==============================================================================

@dataclass
class IncidentTypeSpec:
    """
    Kompletna specyfikacja kategorii zdarzenia ratunkowego.
    Zamiast sztywnych instrukcji if/elif, każda kategoria jest obiektem konfiguracji.
    """
    name: str                                                 # Nazwa techniczna (np. "MAJOR_TRAUMA")
    category_code: str                                        # Kod skrótowy (np. "HIGH")
    priority: Priority                                        # Priorytet Triage (LOW / MEDIUM / HIGH / CRITICAL)
    required_rescuers: int                                    # Wymagana liczba ratowników (np. 2 dla noszy)
    duration_sampler: Callable[[np.random.Generator], float]  # Funkcja losująca czas akcji na miejscu
    description: str                                          # Opis medyczny / operacyjny


# ==============================================================================
# 1. OŚ CZASU (ARRIVAL PROCESS)
# ==============================================================================

class AbstractArrivalProcess(ABC):
    """Interfejs procesu napływu zgłoszeń na osi czasu DES (Discrete Event Simulation)."""

    @abstractmethod
    def get_next_delay(
        self,
        sim_time_minutes: float,
        rng: Optional[np.random.Generator] = None
    ) -> float:
        """
        Zwraca czas w minutach (Delta t) do kolejnego wezwania.
        :param sim_time_minutes: Aktualny moment symulacji (czas SimPy w minutach).
        :param rng: Generator liczb losowych numpy.
        :return: Dodatni odstęp czasu w minutach.
        """
        pass


# ==============================================================================
# 2. OŚ MEDYCZNA / TRIAGE (INCIDENT TYPE SAMPLER)
# ==============================================================================

class AbstractIncidentTypeSampler(ABC):
    """Interfejs kategoryzacji urazów i przydziału priorytetów Triage."""

    @abstractmethod
    def sample_incident_type(
        self,
        rng: Optional[np.random.Generator] = None
    ) -> IncidentTypeSpec:
        """
        Losuje pełną specyfikację zdarzenia ratunkowego.
        :param rng: Generator liczb losowych numpy.
        :return: Obiekt IncidentTypeSpec.
        """
        pass

    @abstractmethod
    def get_category_probabilities(self) -> Dict[str, float]:
        """Zwraca słownik prawdopodobieństw dla zarejestrowanych kategorii."""
        pass


# ==============================================================================
# 3. OŚ PRZESTRZENNA (SPATIAL SAMPLER)
# ==============================================================================

class AbstractSpatialSampler(ABC):
    """Interfejs losowania lokalizacji wypadków na mapie terenu lub sieci szlaków."""

    @abstractmethod
    def sample_location(
        self,
        incident_type: str = "TRAUMA",
        rng: Optional[np.random.Generator] = None
    ) -> Union[str, int]:
        """
        Zwraca identyfikator lokalizacji zdarzenia (np. nazwę węzła szlaku lub ID punktu siatki DEM).
        :param incident_type: Typ zdarzenia (np. "TRAUMA" lub "SEARCH").
        :param rng: Generator liczb losowych numpy.
        :return: Identyfikator węzła/miejsca.
        """
        pass

    @abstractmethod
    def get_probabilities(self, incident_type: str = "TRAUMA") -> Dict[str, float]:
        """Zwraca znormalizowany rozkład prawdopodobieństw dla danej kategorii zdarzenia."""
        pass
