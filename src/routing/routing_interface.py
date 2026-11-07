from abc import ABC, abstractmethod
from typing import List, Union


class AbstractRoutingService(ABC):
    """
    Abstrakcyjny kontrakt serwisu trasowania dla symulacji GOPR.

    Definiuje minimalny zestaw metod, których model agentów (ratownik i dyspozytor)
    wymaga od warstwy przestrzennej (graf OSMnx + funkcja Toblera).
    """

    @abstractmethod
    def get_path(
            self,
            origin: Union[int, str],
            destination: Union[int, str]
    ) -> List[Union[int, str]]:
        """
        Zwraca sekwencję kolejnych węzłów (ścieżkę) od punktu początkowego do docelowego.
        np. [0, 15, 23, 40]
        """
        pass

    @abstractmethod
    def get_edge_travel_time(
            self,
            u: Union[int, str],
            v: Union[int, str],
            speed_factor: float = 1.0
    ) -> float:
        """
        Zwraca fizyczny czas pokonania krawędzi skierowanej (u -> v) w minutach,
        z uwzględnieniem współczynnika prędkości ratownika.
        (W docelowym module tutaj kolega zaimplementuje funkcję Toblera na podstawie nachylenia terenu).
        """
        pass

    @abstractmethod
    def get_travel_time(
            self,
            origin: Union[int, str],
            destination: Union[int, str],
            speed_factor: float = 1.0
    ) -> float:
        """
        Zwraca łączny szacowany czas pokonania trasy (ETA) w minutach.
        Wykorzystywany przez dyspozytora do wyboru najszybszego ratownika do wypadku.
        """
        pass