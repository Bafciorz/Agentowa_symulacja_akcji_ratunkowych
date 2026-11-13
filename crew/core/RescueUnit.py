@dataclass
class RescueUnit(ABC):
    """Klasa bazowa reprezentująca cały zespół ratowniczy jako pojedynczego agenta w symulacji."""
    unit_id: str
    pos: tuple[int, int] = (0, 0)

    c: float = 1.15
    theta_0: float = -2.6
    w: float = 14.5
    d: float = 0.22
    e: float = -0.0018

    off_path_factor: float = 0.67
    steep_slope_factor: float = 1.00

    def calc_move(
        self,
        dist_2d_m: float,
        delta_h_m: float,
        on_path: bool = True,
        eta_roughness: float = 1.0,
        weather: WeatherConditions = WeatherConditions(),
    ) -> tuple[float, float]:
        """Zwraca (prędkość_m_s, czas_przejścia_s) dla pojedynczego odcinka siatki."""
        dist_3d_m = float(np.hypot(dist_2d_m, delta_h_m))
        slope_s = delta_h_m / dist_2d_m
        theta_deg = float(np.degrees(np.arctan(slope_s)))

        v_base = (self.c / (1.0 + ((theta_deg - self.theta_0) / self.w) ** 2)) + self.d + self.e * theta_deg
        v_base = max(v_base, 0.08)

        if on_path:
            k_terrain = 1.0
        else:
            k_terrain = self.off_path_factor / max(1.0, eta_roughness)

        k_steep = self.steep_slope_factor if abs(slope_s) > 0.27 else 1.0

        # 4. Prędkość efektywna i czas
        v_eff = max(v_base * k_terrain * k_steep * weather.env_modifier, 0.05)
        travel_time_sec = dist_3d_m / v_eff

        return v_eff, travel_time_sec