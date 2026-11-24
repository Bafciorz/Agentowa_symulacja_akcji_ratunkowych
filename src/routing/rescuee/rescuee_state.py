import enum
from dataclasses import dataclass, field
from typing import List, Optional, Union


class RescueeBehaviorState(str, enum.Enum):
    """Stany behawioralne osoby zaginionej (wg modelu Markowa WiSAR)."""
    ROUTE_TRAVELING = "ROUTE_TRAVELING"
    OFF_PATH_WANDERING = "OFF_PATH_WANDERING"
    DRAINAGE_FOLLOWING = "DRAINAGE_FOLLOWING"
    STAYING_PUT = "STAYING_PUT"
    IMMOBILIZED = "IMMOBILIZED"


@dataclass
class RescueeState:
    """
    Stan fizyczny i pozycyjny zaginionego turysty (rescuee) na grafie terenu.

    :param starting_node: Węzeł początkowy / punkt ostatniego znanego położenia (LKP).
    :param initial_energy: Początkowy budżet energetyczny w [kJ] (domyślnie 2500.0 kJ).
    :param current_node: Bieżący węzeł na grafie (domyślnie równy starting_node).
    :param energy: Aktualna energia w [kJ] (domyślnie równa initial_energy).
    :param speed_factor: Mnożnik tempa marszu względem ratownika (domyślnie 0.6).
    :param body_mass_kg: Masa ciała W [kg] do równania Pandolfa.
    :param load_mass_kg: Masa ekwipunku L [kg] do równania Pandolfa.
    :param fatigue_ratio: Próg ułamkowy energii poniżej którego rośnie zmęczenie i skłonność do schodzenia w dół.
    """
    starting_node: Union[int, str]
    initial_energy: float = 2500.0
    current_node: Optional[Union[int, str]] = None
    energy: Optional[float] = None
    speed_factor: float = 0.6
    body_mass_kg: float = 75.0
    load_mass_kg: float = 5.0
    fatigue_ratio: float = 0.35
    behavior_state: RescueeBehaviorState = RescueeBehaviorState.ROUTE_TRAVELING
    is_mobile: bool = True
    is_found: bool = False
    prev_node: Optional[Union[int, str]] = None
    elapsed_time_min: float = 0.0
    path_history: List[Union[int, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.initial_energy < 0.0:
            raise ValueError("Początkowa energia nie może być ujemna.")
        if self.speed_factor <= 0.0:
            raise ValueError("Współczynnik prędkości (speed_factor) musi być dodatni.")
        if self.body_mass_kg <= 0.0:
            raise ValueError("Masa ciała musi być dodatnia.")
        if self.load_mass_kg < 0.0:
            raise ValueError("Masa ekwipunku nie może być ujemna.")
        if not 0.0 <= self.fatigue_ratio <= 1.0:
            raise ValueError("Próg zmęczenia (fatigue_ratio) musi mieścić się w przedziale [0.0, 1.0].")

        if self.current_node is None:
            self.current_node = self.starting_node

        if self.energy is None:
            self.energy = float(self.initial_energy)
        else:
            self.energy = max(0.0, float(self.energy))

        if self.energy <= 0.0:
            self.is_mobile = False
            self.behavior_state = RescueeBehaviorState.IMMOBILIZED

        if not self.path_history:
            self.path_history.append(self.current_node)

    @property
    def lkp_node(self) -> Union[int, str]:
        """Alias dla punktu ostatniego znanego położenia (Last Known Point)."""
        return self.starting_node

    @property
    def energy_ratio(self) -> float:
        """Aktualny stosunek pozostałej energii do energii początkowej w [0.0, 1.0]."""
        if self.initial_energy <= 0.0:
            return 0.0
        current = 0.0 if self.energy is None else self.energy
        return max(0.0, min(1.0, current / self.initial_energy))

    @property
    def is_fatigued(self) -> bool:
        """Czy zaginiony przekroczył próg zmęczenia."""
        return self.energy_ratio <= self.fatigue_ratio


@dataclass(frozen=True)
class StepResult:
    """Wynik pojedynczego kroku symulacji ruchu zaginionego."""
    from_node: Union[int, str]
    to_node: Union[int, str]
    action: str  # "MOVE", "STAY_PUT", "IMMOBILIZED"
    behavior_state: RescueeBehaviorState
    travel_time_min: float
    energy_spent_kj: float
    remaining_energy_kj: float
