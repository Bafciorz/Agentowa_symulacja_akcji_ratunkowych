import math
from pathlib import Path
from typing import List, Union, Optional
import networkx as nx

from src.routing.routing_interface import AbstractRoutingService
from src.routing.weather_conditions import WeatherConditions
from data.mappers.terrain_mapper import TerrainGraphMapper


class TerrainRoutingService(AbstractRoutingService):
    """
    Serwis trasowania po grafie terenu (DEM) dla symulacji GOPR / WiSAR.
    
    Odpowiada za fizyczne przeliczanie kosztu przejścia pojedynczego kroku (krawędzi)
    na bazie ukształtowania terenu, równania Lorentza (Campbell & Sullivan) oraz pogody.
    """

    def __init__(self, graph_or_path: Union[nx.DiGraph, str, Path]):
        if isinstance(graph_or_path, (str, Path)):
            mapper = TerrainGraphMapper()
            self.graph: nx.DiGraph = mapper.load_graph(str(graph_or_path))
        elif isinstance(graph_or_path, nx.DiGraph):
            self.graph = graph_or_path
        else:
            raise TypeError("Oczekiwano nx.DiGraph lub ścieżki do pliku grafu GraphML.")

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
        # 1. Sprawdzenie czy węzły istnieją w grafie
        if u not in self.graph:
            raise KeyError(f"Węzeł startowy '{u}' nie istnieje w grafie terenu.")
        if v not in self.graph:
            raise KeyError(f"Węzeł docelowy '{v}' nie istnieje w grafie terenu.")

        # 2. Weryfikacja czy węzły leżą bezpośrednio obok siebie (krawędź u -> v)
        if not self.graph.has_edge(u, v):
            raise ValueError(f"Węzły '{u}' oraz '{v}' nie leżą obok siebie (brak bezpośredniej krawędzi)!")

        edge_data = self.graph.get_edge_data(u, v)

        # 3. Pobranie dystansu 2D oraz różnicy wysokości
        if "distance_2d" in edge_data and "elevation_change" in edge_data:
            dist_2d = float(edge_data["distance_2d"])
            delta_h = float(edge_data["elevation_change"])
        else:
            u_node = self.graph.nodes[u]
            v_node = self.graph.nodes[v]
            dx = float(v_node.get("x_metric", v_node.get("x", 0.0))) - float(u_node.get("x_metric", u_node.get("x", 0.0)))
            dy = float(v_node.get("y_metric", v_node.get("y", 0.0))) - float(u_node.get("y_metric", u_node.get("y", 0.0)))
            dist_2d = math.hypot(dx, dy)
            delta_h = float(v_node.get("z", 0.0)) - float(u_node.get("z", 0.0))

        # Jeśli krawędź ma w atrybutach własne parametry podłoża, mają one pierwszeństwo
        actual_on_path = edge_data.get("on_path", on_path)
        actual_roughness = float(edge_data.get("eta_roughness", eta_roughness))

        # 4. Geometria odcinka
        dist_2d_safe = max(dist_2d, 1e-6)
        dist_3d = math.sqrt(dist_2d_safe**2 + delta_h**2)
        slope_s = delta_h / dist_2d_safe
        theta_deg = math.degrees(math.atan(slope_s))

        # 5. Prędkość bazowa z asymetrycznej krzywej Lorentza (Campbell & Sullivan)
        v_base = (c / (1.0 + ((theta_deg - theta_0) / w) ** 2)) + d + e * theta_deg
        v_base = max(v_base, 0.08)

        # 6. Modyfikator szlaku / nawierzchni (K_terrain)
        if actual_on_path:
            k_terrain = 1.0
        else:
            k_terrain = off_path_factor / max(1.0, actual_roughness)

        # 7. Modyfikator stromości (K_steep) dla nachyleń > 15 st. (|S| > 0.27)
        k_steep = steep_slope_factor if abs(slope_s) > 0.27 else 1.0

        # 8. Modyfikator pogodowy (K_env)
        k_env = weather.env_modifier if hasattr(weather, "env_modifier") else 1.0

        # 9. Prędkość efektywna i czas przejścia
        eff_speed_factor = max(speed_factor, 1e-6)
        v_eff = max(v_base * k_terrain * k_steep * k_env * eff_speed_factor, 0.05)

        travel_time_sec = dist_3d / v_eff
        travel_time_min = travel_time_sec / 60.0

        return travel_time_min

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

    # Alias dla zachowania zgodności
    get_travel_time = get_total_time
