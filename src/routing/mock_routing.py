from typing import List, Union, Optional

from src.routing.routing_interface import AbstractRoutingService
from src.routing.weather_conditions import WeatherConditions


class MockRoutingService(AbstractRoutingService):
    """
    Tymczasowa implementacja serwisu trasowania do testów modelu symulacji GOPR.
    """

    def __init__(self, default_edge_time: float = 3.0):
        self.default_edge_time = default_edge_time

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
        Zwraca czas przejścia krawędzi (u -> v) w minutach dla mocka.
        Sprawdza czy węzły leżą obok siebie.
        """
        is_numeric = False
        try:
            u_int, v_int = int(u), int(v)
            is_numeric = True
        except (ValueError, TypeError):
            pass

        if is_numeric and abs(v_int - u_int) != 1:
            raise ValueError(f"Węzły '{u}' oraz '{v}' nie leżą obok siebie!")

        eff_factor = max(speed_factor, 1e-6)
        k_env = weather.env_modifier if hasattr(weather, "env_modifier") else 1.0
        k_terrain = 1.0 if on_path else (0.67 / max(1.0, eta_roughness))

        return (self.default_edge_time / (k_terrain * k_env * eff_factor))

    def get_path(
        self,
        origin: Union[int, str],
        destination: Union[int, str],
        **kwargs
    ) -> List[Union[int, str]]:
        """
        (Zostawione puste).
        """
        pass

    def get_total_time(
        self,
        origin: Union[int, str],
        destination: Union[int, str],
        **kwargs
    ) -> float:
        """
        (Zostawione puste).
        """
        pass

    get_travel_time = get_total_time
