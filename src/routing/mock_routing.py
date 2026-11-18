from typing import List, Union, Optional

from src.routing.routing_interface import AbstractRoutingService
from src.routing.weather_conditions import WeatherConditions


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
        destination: Union[int, str],
        **kwargs
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
        except (ValueError, TypeError):
            return [origin, destination]

    def get_edge_travel_time(
        self,
        u: Union[int, str],
        v: Union[int, str],
        *args,
        on_path: bool = True,
        eta_roughness: float = 1.0,
        weather: Optional[WeatherConditions] = None,
        speed_factor: float = 1.0,
        **kwargs
    ) -> float:
        """
        Zwraca czas przejścia krawędzi (u -> v) w minutach z uwzględnieniem speed_factor i warunków.
        """
        if args and isinstance(args[0], (int, float)):
            speed_factor = float(args[0])
        elif isinstance(on_path, (int, float)) and not isinstance(on_path, bool):
            speed_factor = float(on_path)

        eff_factor = max(speed_factor, 1e-6)
        k_env = weather.env_modifier if hasattr(weather, "env_modifier") else 1.0
        k_terrain = 1.0 if on_path else (0.67 / max(1.0, eta_roughness))

        return self.default_edge_time / (k_terrain * k_env * eff_factor)

    def get_total_time(
        self,
        origin: Union[int, str],
        destination: Union[int, str],
        *args,
        speed_factor: float = 1.0,
        **kwargs
    ) -> float:
        """
        Zwraca łączny czas pokonania całej trasy na bazie get_path i get_edge_travel_time.
        """
        if args and isinstance(args[0], (int, float)):
            speed_factor = float(args[0])

        path = self.get_path(origin, destination)
        if len(path) <= 1:
            return 0.0

        total = 0.0
        for u, v in zip(path[:-1], path[1:]):
            total += self.get_edge_travel_time(u, v, speed_factor=speed_factor, **kwargs)
        return total

    get_travel_time = get_total_time
