from dataclasses import dataclass


@dataclass
class WeatherConditions:
    """
    Stan pogody dla kroku symulacji / przeliczania krawędzi.
    Oblicza łączny mnożnik warunków atmosferycznych (env_modifier) na podstawie:
    - opadów deszczu (rain_mm_h)
    - pokrywy śnieżnej (snow_cm)
    - prędkości wiatru (wind_kmh)
    - widoczności (visibility_m)
    """
    rain_mm_h: float = 0.0
    snow_cm: float = 0.0
    wind_kmh: float = 0.0
    visibility_m: float = 1000.0

    @property
    def env_modifier(self) -> float:
        # 1. Opady deszczu (K_rain)
        k_rain = 1.0 if self.rain_mm_h == 0.0 else (0.92 if self.rain_mm_h <= 10.0 else 0.65)

        # 2. Pokrywa śnieżna (K_snow)
        if self.snow_cm <= 0.0:
            k_snow = 1.0
        elif self.snow_cm <= 15.0:
            k_snow = 0.80
        elif self.snow_cm <= 30.0:
            k_snow = 0.50
        else:
            k_snow = 0.30

        # 3. Wiatr (K_wind)
        k_wind = 1.0 if self.wind_kmh < 30.0 else (0.88 if self.wind_kmh <= 70.0 else 0.50)

        # 4. Widoczność (K_vis) - mgła / noc
        k_vis = 1.0 if self.visibility_m >= 50.0 else 0.75

        return k_rain * k_snow * k_wind * k_vis
