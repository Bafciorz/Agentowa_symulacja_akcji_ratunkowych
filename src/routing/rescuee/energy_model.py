from abc import ABC, abstractmethod
from typing import Optional

from src.routing.weather_conditions import WeatherConditions


class AbstractEnergyModel(ABC):
    """Kontrakt modelu wydatku energetycznego osoby zaginionej."""

    @abstractmethod
    def calculate_move_energy(
        self,
        dist_2d_m: float,
        dist_3d_m: float,
        delta_h_m: float,
        travel_time_min: float,
        body_mass_kg: float,
        load_mass_kg: float,
        eta_roughness: float = 1.0,
    ) -> float:
        """Zwraca wydatek energetyczny [kJ] potrzebny do pokonania odcinka."""
        pass

    @abstractmethod
    def calculate_rest_energy(
        self,
        duration_min: float,
        weather: Optional[WeatherConditions] = None,
    ) -> float:
        """Zwraca wydatek energetyczny [kJ] podczas postoju z uwzględnieniem wychłodzenia."""
        pass


class PandolfEnergyModel(AbstractEnergyModel):
    """
    Model wydatku energetycznego oparty na równaniu metabolicznym Pandolfa (1977):
        M = 1.5*W + 2.0*(W + L)*(L/W)^2 + eta*(W + L)*(1.5*v^2 + 0.35*v*G_+) [W]
        Delta_E = (M * Delta_t) / 1000 [kJ]

    Podczas postoju stosowany jest spoczynkowy drenaż metaboliczny (~100 W)
    zwiększany przez wychłodzenie w trudnych warunkach pogodowych.
    """

    def __init__(self, resting_watts: float = 100.0):
        self.resting_watts = max(float(resting_watts), 1.0)

    def calculate_move_energy(
        self,
        dist_2d_m: float,
        dist_3d_m: float,
        delta_h_m: float,
        travel_time_min: float,
        body_mass_kg: float,
        load_mass_kg: float,
        eta_roughness: float = 1.0,
    ) -> float:
        """
        Oblicza wydatek energetyczny marszu w [kJ] wg wzoru Pandolfa (1977).
        """
        if travel_time_min <= 0.0 or dist_3d_m <= 0.0:
            return 0.0

        dt_sec = travel_time_min * 60.0
        v_ms = dist_3d_m / dt_sec

        dist_2d_safe = max(dist_2d_m, 1e-6)
        grade_pos_pct = max(0.0, (delta_h_m / dist_2d_safe) * 100.0)

        w_kg = max(body_mass_kg, 1.0)
        l_kg = max(load_mass_kg, 0.0)
        eta = max(eta_roughness, 1.0)

        metabolic_watts = (
            1.5 * w_kg
            + 2.0 * (w_kg + l_kg) * ((l_kg / w_kg) ** 2)
            + eta * (w_kg + l_kg) * (1.5 * (v_ms ** 2) + 0.35 * v_ms * grade_pos_pct)
        )

        return (metabolic_watts * dt_sec) / 1000.0

    def calculate_rest_energy(
        self,
        duration_min: float,
        weather: Optional[WeatherConditions] = None,
    ) -> float:
        """
        Oblicza wydatek energetyczny spoczynku w [kJ] (bazowo ~100 W * mnożnik chłodu).
        """
        if duration_min <= 0.0:
            return 0.0

        dt_sec = duration_min * 60.0
        cold_factor = self._cold_multiplier(weather)
        return (self.resting_watts * cold_factor * dt_sec) / 1000.0

    @staticmethod
    def _cold_multiplier(weather: Optional[WeatherConditions]) -> float:
        """Mnożnik dodatkowego kosztu termoregulacji w niesprzyjającej pogodzie."""
        if weather is None:
            return 1.0

        penalty = 0.0
        if weather.rain_mm_h > 0.0:
            penalty += 0.25 if weather.rain_mm_h <= 10.0 else 0.45

        if weather.snow_cm > 0.0:
            penalty += 0.30 if weather.snow_cm <= 15.0 else 0.50

        if weather.wind_kmh >= 30.0:
            penalty += 0.25 if weather.wind_kmh <= 70.0 else 0.45

        return 1.0 + penalty
