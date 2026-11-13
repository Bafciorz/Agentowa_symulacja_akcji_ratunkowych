from typing import List, Union

from src.routing.routing_interface import AbstractRoutingService


class MockRoutingService(AbstractRoutingService):
    """
    Tymczasowa implementacja serwisu trasowania do testów modelu symulacji GOPR.
    Generuje sztuczne ścieżki i stałe czasy krawędzi bez konieczności ładowania
    grafu OSMnx czy modelu DEM Toblera.
    """

    def __init__(self, default_edge_time: float = 3.0):
        self.default_edge_time = default_edge_time

    def get_path(
        self,
        origin: Union[int, str],
        destination: Union[int, str]
    ) -> List[Union[int, str]]:
        """
        Zwraca sekwencję węzłów.
        Dla węzłów liczbowych (np. 0 do 4) zwraca: [0, 1, 2, 3, 4].
        Dla węzłów tekstowych zwraca parę: [origin, destination].
        """
        if origin == destination:
            return [origin]

        try:
            u, v = int(origin), int(destination)
            step = 1 if v >= u else -1
            return list(range(u, v + step, step))
        except ValueError:
            return [origin, destination]

    def get_edge_travel_time(
        self,
        u: Union[int, str],
        v: Union[int, str],
        speed_factor: float = 1.0
    ) -> float:
        """
        Zwraca czas przejścia krawędzi (u -> v) w minutach z uwzględnieniem speed_factor.
        """
        return self.default_edge_time / speed_factor

    def get_travel_time(
        self,
        origin: Union[int, str],
        destination: Union[int, str],
        speed_factor: float = 1.0
    ) -> float:
        """
        Zwraca łączny czas podróży (ETA) w minutach dla całej ścieżki.
        """
        path = self.get_path(origin, destination)
        if len(path) <= 1:
            return 0.0
        return (len(path) - 1) * self.get_edge_travel_time(path[0], path[1], speed_factor)
