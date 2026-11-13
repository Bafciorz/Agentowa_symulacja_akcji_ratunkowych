@dataclass
class WeatherConditions:
    """Stan pogody w danym kroku symulacji DES."""
    rain_mm_h: float = 0.0
    snow_cm: float = 0.0
    wind_kmh: float = 0.0
    visibility_m: float = 1000.0

    @property
    def env_modifier(self) -> float:
        k_rain = 1.0 if self.rain_mm_h == 0 else (0.92 if self.rain_mm_h <= 10.0 else 0.65)

        if self.snow_cm <= 0:
            k_snow = 1.0
        elif self.snow_cm <= 15.0:
            k_snow = 0.80
        elif self.snow_cm <= 30.0:
            k_snow = 0.50
        else:
            k_snow = 0.30

        k_wind = 1.0 if self.wind_kmh < 30.0 else (0.88 if self.wind_kmh <= 70.0 else 0.50)
        k_vis = 1.0 if self.visibility_m >= 50.0 else 0.75  # Czołówki w nocy / mgle

        return k_rain * k_snow * k_wind * k_vis