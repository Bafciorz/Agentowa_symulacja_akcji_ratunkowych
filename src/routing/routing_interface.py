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

        Model opiera się na asymetrycznej krzywej Lorentza (Campbell & Sullivan, 2019/2020)
        oraz mnożnikach środowiskowo-terenowych (Irmischer-Clarke / WiSAR):
            v_base(theta) = c / (1 + ((theta - theta_0) / w)^2) + d + e * theta
            v_eff = max(v_base * K_terrain * K_steep * K_env * speed_factor, 0.05) [m/s]
            travel_time = (dist_3d / v_eff) / 60.0 [min]

        :param u: Identyfikator węzła początkowego (musi istnieć w grafie).
        :param v: Identyfikator węzła docelowego (musi bezpośrednio sąsiadować z u).
        :param on_path: Czy ruch odbywa się po szlaku (True) czy na przełaj (False).
        :param eta_roughness: Współczynnik oporu/szorstkości podłoża poza szlakiem (eta >= 1.0; np. 1.0 hala/ścieżka, 1.5 runo leśne, 2.2 wiatrołomy).
        :param weather: Obiekt WeatherConditions (opcjonalny) – redukuje prędkość przez deszcz, śnieg, wiatr i mgłę/noc.
        :param speed_factor: Dodatkowy mnożnik tempa marszu ratownika (domyślnie 1.0).

        Parametry asymetrycznej krzywej Lorentza (Campbell & Sullivan):
        :param c: Amplituda krzywej [m/s] – wysokość piku prędkości względem asymptoty d (domyślnie 1.15; 0.55 dla noszy, 1.42 dla szybkiego patrolu).
        :param theta_0: Kąt optymalnego spadku [°] – nachylenie stoku, przy którym marsz jest najszybszy (domyślnie -2.6°; lekki spadek w dół).
        :param w: Szerokość połówkowa krzywej [°] – tolerancja na nachylenie (domyślnie 14.5°; jak szybko prędkość spada wraz ze stromizną).
        :param d: Przesunięcie pionowe [m/s] – minimalna prędkość bazowa na bardzo stromych stokach (domyślnie 0.22; asymptota).
        :param e: Współczynnik asymetrii liniowej [m/(s*°)] – kara za podejścia pod górę względem zejść (domyślnie -0.0018, e < 0).

        Specyficzne mnożniki ukształtowania terenu:
        :param off_path_factor: Bazowy mnożnik prędkości poza szlakiem (domyślnie 0.67; 0.45 dla noszy, 0.75 dla lekkiego patrolu).
        :param steep_slope_factor: Mnożnik redukcyjny na stokach stromych (|S| > 0.27, czyli |theta| > 15°) (domyślnie 1.0; 0.35 dla transportu noszy z asekuracją linową).

        :return: Czas pokonania krawędzi u -> v w minutach.
        :raises KeyError: Jeśli węzeł u lub v nie istnieje w grafie.
        :raises ValueError: Jeśli węzły u i v nie leżą bezpośrednio obok siebie.
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
