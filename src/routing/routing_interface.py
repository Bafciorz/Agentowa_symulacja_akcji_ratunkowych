from abc import ABC, abstractmethod
from typing import List, Union, Optional

from src.routing.weather_conditions import WeatherConditions


class AbstractRoutingService(ABC):
    """
    Abstrakcyjny kontrakt serwisu trasowania dla symulacji GOPR / WiSAR.
    Definiuje operacje trasowania (przeliczanie kosztów krawędzi, wyznaczanie ścieżek
    i łącznego czasu dojścia) wykorzystywane przez agentów (ratownik, dyspozytor).
    """

    @abstractmethod
    def get_edge_travel_time(
        self,
        u: Union[int, str],
        v: Union[int, str],
        on_path: bool = True,
        eta_roughness: float = 1.0,
        weather: Optional[WeatherConditions] = None,
        speed_factor: float = 1.0,
        c: float = 1.15,
        theta_0: float = -2.6,
        w: float = 14.5,
        d: float = 0.22,
        e: float = -0.0018,
        off_path_factor: float = 0.67,
        steep_slope_factor: float = 1.0,
        **kwargs
    ) -> float:
        """
        Zwraca fizyczny czas pokonania odcinka (krawędzi) między dwoma sąsiednimi węzłami u -> v w minutach.
        """
        pass

    @abstractmethod
    def get_path(
        self,
        origin: Union[int, str],
        destination: Union[int, str],
        **kwargs
    ) -> List[Union[int, str]]:
        """
        Zwraca kolejność przechodzenia węzłów (ścieżkę) od origin do destination.
        """
        pass

    @abstractmethod
    def get_total_time(
        self,
        origin: Union[int, str],
        destination: Union[int, str],
        **kwargs
    ) -> float:
        """
        Zwraca łączny czas pokonania całej trasy na bazie get_path i get_edge_travel_time.
        """
        pass

    def get_travel_time(
        self,
        origin: Union[int, str],
        destination: Union[int, str],
        **kwargs
    ) -> float:
        """
        Alias zachowujący pełną kompatybilność z silnikiem symulacji i dyspozytorem.
        """
        return self.get_total_time(origin, destination, **kwargs)
