import math
from pathlib import Path
from typing import Dict, Any, List, Tuple, Union, Optional
import networkx as nx

from src.routing.routing_interface import AbstractRoutingService
from src.routing.weather_conditions import WeatherConditions


# ==============================================================================
# GŁÓWNE WĘZŁY I PUNKTY ORIENTACYJNE GORCÓW (BAZY GOPR, SZCZYTY, SCHRONISKA)
# ==============================================================================
GORCE_TRAIL_NODES: Dict[str, Dict[str, Any]] = {
    "Schronisko_Turbacz": {
        "name": "Schronisko PTTK Turbacz",
        "lat": 49.5428,
        "lon": 20.1116,
        "z": 1283.0,
        "is_base": True,
        "desc": "Główna Stacja Ratunkowa GOPR w Gorcach (dyżur całoroczny)"
    },
    "Turbacz_Szczyt": {
        "name": "Turbacz (Szczyt)",
        "lat": 49.5430,
        "lon": 20.1118,
        "z": 1310.0,
        "is_base": False,
        "desc": "Najwyższy szczyt Gorców (1310 m n.p.m.)"
    },
    "Hala_Dluga": {
        "name": "Hala Długa",
        "lat": 49.5445,
        "lon": 20.1170,
        "z": 1210.0,
        "is_base": False,
        "desc": "Rozległa hala pasterska pod Turbaczem (szlak czerwony GSB)"
    },
    "Polana_Gabrowska": {
        "name": "Polana Gabrowska",
        "lat": 49.5460,
        "lon": 20.1320,
        "z": 1265.0,
        "is_base": False,
        "desc": "Węzeł szlaków czerwonego (GSB), zielonego i żółtego"
    },
    "Kiczora": {
        "name": "Kiczora (Szczyt)",
        "lat": 49.5432,
        "lon": 20.1440,
        "z": 1282.0,
        "is_base": False,
        "desc": "Drugi szczyt pasma Turbacza, widok na Tatry i Babią Górę"
    },
    "Przelecz_Knurowska": {
        "name": "Przełęcz Knurowska",
        "lat": 49.5165,
        "lon": 20.1870,
        "z": 846.0,
        "is_base": False,
        "desc": "Przełęcz drogowa, punkt styku z karetkami Pogotowia Ratunkowego"
    },
    "Stare_Wierchy": {
        "name": "Schronisko Stare Wierchy",
        "lat": 49.5600,
        "lon": 20.0240,
        "z": 968.0,
        "is_base": True,
        "desc": "Podstacja dyżurna GOPR na zachodnim ramieniu pasma"
    },
    "Obidowiec": {
        "name": "Obidowiec",
        "lat": 49.5530,
        "lon": 20.0650,
        "z": 1106.0,
        "is_base": False,
        "desc": "Szczyt na szlaku czerwonym między Turbaczem a Starymi Wierchami"
    },
    "Kowaniec_NowyTarg": {
        "name": "Kowaniec (Nowy Targ)",
        "lat": 49.5080,
        "lon": 20.0610,
        "z": 620.0,
        "is_base": True,
        "desc": "Dolna baza GOPR w Nowym Targu, mobilizacja ratowników i dojazd quadem"
    },
    "Jaworzyna_Kamienicka": {
        "name": "Jaworzyna Kamienicka",
        "lat": 49.5540,
        "lon": 20.1480,
        "z": 1288.0,
        "is_base": False,
        "desc": "Polana z zabytkową Kapliczką Bulandy (szlak zielony GPN)"
    },
    "Kudlon": {
        "name": "Kudłoń (Szczyt)",
        "lat": 49.5740,
        "lon": 20.1570,
        "z": 1225.0,
        "is_base": False,
        "desc": "Północny rejon Gorczańskiego Parku Narodowego, skalne ostańce"
    },
    "Dolina_Kamienicy_Wiatrolomy": {
        "name": "Dolina Kamienicy (Poza szlakiem)",
        "lat": 49.5650,
        "lon": 20.1600,
        "z": 950.0,
        "is_base": False,
        "desc": "Teren pozaszlakowy: gęsty las, strome żleby i wiatrołomy świerkowe"
    }
}


# ==============================================================================
# GŁÓWNE SZLAKI I ŚCIEŻKI GORCÓW (POŁĄCZENIA KRAWĘDZIOWE)
# ==============================================================================
GORCE_TRAIL_EDGES: List[Dict[str, Any]] = [
    # Szlak Czerwony - Główny Szlak Beskidzki (GSB) odcinek Turbacz - Knurowska
    {"u": "Schronisko_Turbacz", "v": "Hala_Dluga", "trail_name": "Główny Szlak Beskidzki (GSB)", "color": "red", "on_path": True, "eta": 1.0},
    {"u": "Hala_Dluga", "v": "Polana_Gabrowska", "trail_name": "Główny Szlak Beskidzki (GSB)", "color": "red", "on_path": True, "eta": 1.0},
    {"u": "Polana_Gabrowska", "v": "Kiczora", "trail_name": "Główny Szlak Beskidzki (GSB)", "color": "red", "on_path": True, "eta": 1.0},
    {"u": "Kiczora", "v": "Przelecz_Knurowska", "trail_name": "Główny Szlak Beskidzki (GSB)", "color": "red", "on_path": True, "eta": 1.0},

    # Szlak Czerwony - GSB zachód: Turbacz - Obidowiec - Stare Wierchy
    {"u": "Schronisko_Turbacz", "v": "Obidowiec", "trail_name": "Główny Szlak Beskidzki (Zachód)", "color": "red", "on_path": True, "eta": 1.0},
    {"u": "Obidowiec", "v": "Stare_Wierchy", "trail_name": "Główny Szlak Beskidzki (Zachód)", "color": "red", "on_path": True, "eta": 1.0},

    # Szlak Czerwony dojściowy na wierzchołek Turbacza
    {"u": "Schronisko_Turbacz", "v": "Turbacz_Szczyt", "trail_name": "Szlak dojściowy na Szczyt", "color": "red", "on_path": True, "eta": 1.0},

    # Szlak Żółty z Nowego Targu (Kowaniec) do Schroniska na Turbaczu
    {"u": "Kowaniec_NowyTarg", "v": "Schronisko_Turbacz", "trail_name": "Szlak Żółty (Nowy Targ - Turbacz)", "color": "gold", "on_path": True, "eta": 1.0},

    # Szlak Zielony - Gorczański Park Narodowy (Polana Gabrowska -> Jaworzyna -> Kudłoń)
    {"u": "Polana_Gabrowska", "v": "Jaworzyna_Kamienicka", "trail_name": "Szlak Zielony GPN", "color": "green", "on_path": True, "eta": 1.0},
    {"u": "Jaworzyna_Kamienicka", "v": "Kudlon", "trail_name": "Szlak Zielony GPN", "color": "green", "on_path": True, "eta": 1.0},

    # Teren pozaszlakowy (Dolina Kamienicy - wiatrołomy, zwalone pnie, strome zbocze)
    {
        "u": "Kudlon",
        "v": "Dolina_Kamienicy_Wiatrolomy",
        "trail_name": "Teren pozaszlakowy (wiatrołomy i zwalone pnie)",
        "color": "black",
        "on_path": False,
        "eta": 2.2,
        "steep_factor": 0.55
    }
]


def build_gorce_trails_graph() -> nx.DiGraph:
    """
    Tworzy skierowany graf topologiczny głównych szlaków i baz GOPR w Gorcach (nx.DiGraph).
    Krawędzie są dwukierunkowe z rzeczywistą fizyką podejść (+delta_h) i zejść (-delta_h).
    """
    G = nx.DiGraph()

    # 1. Dodawanie węzłów z atrybutami geograficznymi
    for node_id, data in GORCE_TRAIL_NODES.items():
        # Aproksymacja metryczna (EPSG:2180 w rejonie Gorców: lat ~49.5°, lon ~20.1°)
        x_m = data["lon"] * 72200.0
        y_m = data["lat"] * 111200.0
        G.add_node(
            node_id,
            name=data["name"],
            lat=data["lat"],
            lon=data["lon"],
            x=data["lon"],
            y=data["lat"],
            x_metric=x_m,
            y_metric=y_m,
            z=data["z"],
            is_base=data.get("is_base", False),
            desc=data.get("desc", "")
        )

    # 2. Dodawanie krawędzi (w obu kierunkach u <-> v)
    for edge in GORCE_TRAIL_EDGES:
        u, v = edge["u"], edge["v"]
        u_node = G.nodes[u]
        v_node = G.nodes[v]

        dx = (v_node["lon"] - u_node["lon"]) * 72200.0
        dy = (v_node["lat"] - u_node["lat"]) * 111200.0
        dist_2d = math.hypot(dx, dy)
        dist_2d = max(dist_2d, 10.0)

        delta_h_forward = v_node["z"] - u_node["z"]
        delta_h_backward = -delta_h_forward

        dist_3d_f = math.sqrt(dist_2d**2 + delta_h_forward**2)
        dist_3d_b = math.sqrt(dist_2d**2 + delta_h_backward**2)

        # Krawędź u -> v
        G.add_edge(
            u, v,
            trail_name=edge["trail_name"],
            color=edge["color"],
            on_path=edge["on_path"],
            eta_roughness=edge.get("eta", 1.0),
            steep_slope_factor=edge.get("steep_factor", 1.0),
            distance_2d=dist_2d,
            elevation_change=delta_h_forward,
            distance_3d=dist_3d_f
        )

        # Krawędź przeciwna v -> u (odwrotna deniwelacja)
        G.add_edge(
            v, u,
            trail_name=edge["trail_name"],
            color=edge["color"],
            on_path=edge["on_path"],
            eta_roughness=edge.get("eta", 1.0),
            steep_slope_factor=edge.get("steep_factor", 1.0),
            distance_2d=dist_2d,
            elevation_change=delta_h_backward,
            distance_3d=dist_3d_b
        )

    return G


class GorceTrailRoutingService(AbstractRoutingService):
    """
    Serwis trasowania po sieci szlaków Gorców wykorzystujący:
    - Rzeczywistą topologię szlaków (GSB, szlak żółty, zielony, teren pozaszlakowy)
    - Fizykę Campbell & Sullivan (asymetryczna krzywa Lorentza dla podejść/zejść)
    - Opory nawierzchni WiSAR (szlak vs wiatrołomy)
    - Modyfikatory meteorologiczne WeatherConditions (śnieg, wiatr, widoczność)
    - Algorytm Dijkstry do wyszukiwania ścieżki o minimalnym czasie przejścia
    """

    def __init__(self, graph: Optional[nx.DiGraph] = None, default_weather: Optional[WeatherConditions] = None):
        self.graph = graph if graph is not None else build_gorce_trails_graph()
        self.weather = default_weather or WeatherConditions()

    def get_edge_travel_time(
        self,
        u: Union[int, str],
        v: Union[int, str],
        *args,
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
        """Oblicza czas pokonania krawędzi w minutach na podstawie fizyki Campbell & Sullivan."""
        if u not in self.graph or v not in self.graph:
            raise KeyError(f"Węzeł {u} lub {v} nie istnieje w grafie szlaków.")

        if not self.graph.has_edge(u, v):
            raise ValueError(f"Brak bezpośredniej krawędzi między {u} i {v}.")

        # Obsługa przekazywania speed_factor jako 3. argumentu pozycyjnego
        if args and isinstance(args[0], (int, float)):
            speed_factor = float(args[0])
        elif isinstance(on_path, (int, float)) and not isinstance(on_path, bool):
            speed_factor = float(on_path)
            on_path = True

        edge_data = self.graph.get_edge_data(u, v)

        dist_2d = float(edge_data.get("distance_2d", 100.0))
        delta_h = float(edge_data.get("elevation_change", 0.0))
        actual_on_path = edge_data.get("on_path", on_path)
        actual_roughness = float(edge_data.get("eta_roughness", eta_roughness))
        actual_steep = float(edge_data.get("steep_slope_factor", steep_slope_factor))

        dist_2d_safe = max(dist_2d, 1.0)
        dist_3d = math.sqrt(dist_2d_safe**2 + delta_h**2)
        slope_s = delta_h / dist_2d_safe
        theta_deg = math.degrees(math.atan(slope_s))

        # Krzywa Lorentza (Campbell & Sullivan)
        v_base = (c / (1.0 + ((theta_deg - theta_0) / w) ** 2)) + d + e * theta_deg
        v_base = max(v_base, 0.08)

        # Czynniki nawierzchni i terenu
        k_terrain = 1.0 if actual_on_path else (off_path_factor / max(1.0, actual_roughness))
        k_steep = actual_steep if abs(slope_s) > 0.27 else 1.0

        current_weather = weather if weather is not None else self.weather
        k_env = current_weather.env_modifier if hasattr(current_weather, "env_modifier") else 1.0

        eff_speed = max(speed_factor, 1e-6)
        v_eff = max(v_base * k_terrain * k_steep * k_env * eff_speed, 0.05)

        travel_time_sec = dist_3d / v_eff
        return travel_time_sec / 60.0

    def _get_edge_weight(self, u: str, v: str, speed_factor: float = 1.0, weather: Optional[WeatherConditions] = None) -> float:
        return self.get_edge_travel_time(u, v, speed_factor=speed_factor, weather=weather)

    def get_path(
        self,
        origin: Union[int, str],
        destination: Union[int, str],
        speed_factor: float = 1.0,
        weather: Optional[WeatherConditions] = None,
        **kwargs
    ) -> List[Union[int, str]]:
        """Zwraca optymalną czasowo ścieżkę (sekwencję węzłów) wg algorytmu Dijkstry."""
        if origin == destination:
            return [origin]

        try:
            path = nx.shortest_path(
                self.graph,
                source=origin,
                target=destination,
                weight=lambda u, v, _: self._get_edge_weight(u, v, speed_factor=speed_factor, weather=weather)
            )
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return [origin, destination]

    def get_total_time(
        self,
        origin: Union[int, str],
        destination: Union[int, str],
        speed_factor: float = 1.0,
        weather: Optional[WeatherConditions] = None,
        **kwargs
    ) -> float:
        """Zwraca łączny czas pokonania trasy w minutach."""
        if origin == destination:
            return 0.0

        path = self.get_path(origin, destination, speed_factor=speed_factor, weather=weather)
        if len(path) <= 1:
            return 0.0

        total_time = 0.0
        for u, v in zip(path[:-1], path[1:]):
            total_time += self.get_edge_travel_time(u, v, speed_factor=speed_factor, weather=weather)
        return total_time

    get_travel_time = get_total_time

    def generate_interactive_map(
        self,
        output_path: str = "gorce_rescue_map.html",
        incidents: Optional[List[Any]] = None,
        rescuer_paths: Optional[Dict[str, List[Tuple[str, str]]]] = None
    ) -> str:
        """
        Generuje w 100% samodzielną interaktywną mapę HTML (Leaflet.js)
        z podkładem topograficznym OpenTopoMap Gorców, szlakami, bazami GOPR i zdarzeniami.
        """
        nodes_js = []
        for nid, data in self.graph.nodes(data=True):
            nodes_js.append({
                "id": nid,
                "name": data.get("name", nid),
                "lat": data["lat"],
                "lon": data["lon"],
                "z": data["z"],
                "is_base": data.get("is_base", False),
                "desc": data.get("desc", "")
            })

        edges_js = []
        for u, v, d in self.graph.edges(data=True):
            # Dodajemy tylko jedną krawędź na parę (aby nie duplikować kresek na mapie)
            if str(u) < str(v):
                u_node = self.graph.nodes[u]
                v_node = self.graph.nodes[v]
                edges_js.append({
                    "u": u,
                    "v": v,
                    "coords": [[u_node["lat"], u_node["lon"]], [v_node["lat"], v_node["lon"]]],
                    "trail_name": d.get("trail_name", "Szlak"),
                    "color": d.get("color", "red"),
                    "on_path": d.get("on_path", True),
                    "dist_m": round(d.get("distance_3d", 0.0), 1)
                })

        incidents_js = []
        if incidents:
            for inc in incidents:
                target_nid = inc.target_node
                if target_nid in self.graph:
                    tnode = self.graph.nodes[target_nid]
                    incidents_js.append({
                        "id": inc.incident_id,
                        "node_name": tnode.get("name", target_nid),
                        "lat": tnode["lat"],
                        "lon": tnode["lon"],
                        "priority": inc.priority.name,
                        "required": inc.required_rescuers,
                        "duration": inc.rescue_duration,
                        "is_resolved": inc.is_resolved
                    })

        import json
        nodes_json_str = json.dumps(nodes_js, ensure_ascii=False)
        edges_json_str = json.dumps(edges_js, ensure_ascii=False)
        incidents_json_str = json.dumps(incidents_js, ensure_ascii=False)

        html_content = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <title>GOPR Gorce - Symulacja Akcji Ratunkowych (DES + ABM)</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
        #map {{ width: 100vw; height: 100vh; }}
        .hud-panel {{
            position: absolute;
            top: 20px;
            right: 20px;
            z-index: 1000;
            background: rgba(255, 255, 255, 0.95);
            padding: 16px 20px;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.25);
            max-width: 360px;
            backdrop-filter: blur(8px);
            border: 1px solid #e2e8f0;
        }}
        .hud-title {{ font-size: 16px; font-weight: 700; color: #1e293b; margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }}
        .hud-sub {{ font-size: 12px; color: #64748b; margin-bottom: 12px; }}
        .badge {{ display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
        .badge-critical {{ background: #fee2e2; color: #991b1b; }}
        .badge-high {{ background: #ffedd5; color: #9a3412; }}
        .badge-low {{ background: #e0f2fe; color: #075985; }}
        .legend-item {{ display: flex; align-items: center; gap: 8px; font-size: 12px; margin-bottom: 5px; color: #334155; }}
        .legend-color {{ width: 18px; height: 4px; border-radius: 2px; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div class="hud-panel">
        <div class="hud-title">
            <span>GOPR GORCE - DYŻUR OPERACYJNY</span>
        </div>
        <div class="hud-sub">Symulacja Agentowa DES (SimPy) + Fizyka Terenu (Campbell & Sullivan)</div>
        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 10px 0;">
        <div style="font-weight: 600; font-size: 13px; margin-bottom: 6px; color: #0f172a;">Legenda Szlaków:</div>
        <div class="legend-item"><div class="legend-color" style="background: #dc2626;"></div> Główny Szlak Beskidzki (GSB)</div>
        <div class="legend-item"><div class="legend-color" style="background: #16a34a;"></div> Szlak Zielony GPN (Kudłoń)</div>
        <div class="legend-item"><div class="legend-color" style="background: #eab308;"></div> Szlak Żółty (Kowaniec - Turbacz)</div>
        <div class="legend-item"><div class="legend-color" style="background: #000; border: 1px dashed #666;"></div> Teren pozaszlakowy (wiatrołomy)</div>
        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 10px 0;">
        <div style="font-size: 11px; color: #475569;">
            <b>Stacje GOPR:</b> Schronisko Turbacz, Kowaniec, Stare Wierchy<br>
            <b>Model terenu:</b> Asymetria Lorentza + WiSAR + Pogoda
        </div>
    </div>

    <script>
        const map = L.map('map').setView([49.544, 20.115], 13);

        // Podkład Topograficzny OpenTopoMap (doskonały do gór ze strefami poziomic)
        const topoLayer = L.tileLayer('https://{{s}}.tile.opentopomap.org/{{z}}/{{x}}/{{y}}.png', {{
            maxZoom: 17,
            attribution: 'Map data: &copy; OpenStreetMap, SRTM | Map style: &copy; OpenTopoMap'
        }}).addTo(map);

        const nodes = {nodes_json_str};
        const edges = {edges_json_str};
        const incidents = {incidents_json_str};

        // Rysowanie krawędzi (szlaków)
        edges.forEach(e => {{
            const isDash = !e.on_path;
            const poly = L.polyline(e.coords, {{
                color: e.color === 'black' ? '#000000' : e.color,
                weight: isDash ? 3 : 5,
                dashArray: isDash ? '6, 8' : null,
                opacity: 0.85
            }}).addTo(map);

            poly.bindPopup(`<b>${{e.trail_name}}</b><br>Dystans 3D: ${{e.dist_m}} m<br>${{e.on_path ? 'Szlak znakowany' : '[UWAGA] Trudny teren pozaszlakowy'}}`);
        }});

        // Rysowanie węzłów
        nodes.forEach(n => {{
            const markerColor = n.is_base ? '#1d4ed8' : '#475569';
            const radius = n.is_base ? 9 : 6;
            const circle = L.circleMarker([n.lat, n.lon], {{
                radius: radius,
                fillColor: markerColor,
                color: '#ffffff',
                weight: 2,
                opacity: 1,
                fillOpacity: 0.95
            }}).addTo(map);

            circle.bindPopup(`<b>${{n.name}}</b> (${{n.z}} m n.p.m.)<br>${{n.desc}}`);
        }});

        // Rysowanie zdarzeń ratunkowych
        incidents.forEach(inc => {{
            let pColor = '#0284c7';
            if (inc.priority === 'CRITICAL') pColor = '#dc2626';
            else if (inc.priority === 'HIGH') pColor = '#ea580c';

            const incMarker = L.circleMarker([inc.lat, inc.lon], {{
                radius: 12,
                fillColor: pColor,
                color: '#ffffff',
                weight: 3,
                opacity: 1,
                fillOpacity: 0.9
            }}).addTo(map);

            const statusTxt = inc.is_resolved ? '[ROZWIĄZANY]' : '[W TRAKCIE / KOLEJKA]';
            incMarker.bindPopup(`
                <div style="font-family: sans-serif;">
                    <b style="color: ${{pColor}};">[${{inc.priority}}] ${{inc.id}}</b><br>
                    <b>Miejsce:</b> ${{inc.node_name}}<br>
                    <b>Wymaganych ratowników:</b> ${{inc.required}}<br>
                    <b>Czas akcji na miejscu:</b> ${{inc.duration}} min<br>
                    <b>Status:</b> ${{statusTxt}}
                </div>
            `);
        }});
    </script>
</body>
</html>
"""
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(html_content, encoding="utf-8")
        return str(out_file.resolve())
