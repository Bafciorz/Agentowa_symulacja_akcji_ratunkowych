from abc import ABC, abstractmethod
from typing import List, Union, Optional

from src.routing.weather_conditions import WeatherConditions


class AbstractRoutingService(ABC):
    """
    Abstrakcyjny kontrakt serwisu trasowania dla symulacji GOPR / WiSAR.
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
        **kwargs
    ) -> float:
        """
        Zwraca czas pokonania trasy od węzła u do węzła v, KTÓRE LEŻĄ OBOK SIEBIE (w minutach).
        
        Obliczenia bazują bezpośrednio na nachyleniu terenu i asymetrycznym modelu Lorentza (Campbell & Sullivan)
        z uwzględnieniem nawierzchni (szlak/poza szlakiem, szorstkość) oraz warunków pogodowych.
        Jeżeli węzły u i v nie są bezpośrednimi sąsiadami, metoda powinna zgłosić błąd.
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
        (Zostawione puste - do zaimplementowania w kolejnym kroku przy użyciu algorytmu A*).
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
        (Zostawione puste - do zaimplementowania w kolejnym kroku).
        """
        pass
