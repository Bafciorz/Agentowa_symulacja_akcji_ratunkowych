import pytest
from pathlib import Path
from src.routing import (
    GorceTrailRoutingService,
    build_gorce_trails_graph,
    WeatherConditions
)


def test_gorce_trails_graph_structure():
    G = build_gorce_trails_graph()
    assert G.number_of_nodes() >= 10
    assert G.number_of_edges() >= 18

    # Stacje GOPR
    assert G.nodes["Schronisko_Turbacz"]["is_base"] is True
    assert G.nodes["Kowaniec_NowyTarg"]["is_base"] is True
    assert G.nodes["Stare_Wierchy"]["is_base"] is True

    # Wysokości szczytów
    assert G.nodes["Turbacz_Szczyt"]["z"] == 1310.0
    assert G.nodes["Kiczora"]["z"] == 1282.0


def test_campbell_sullivan_asymmetry_and_physics():
    routing = GorceTrailRoutingService()

    # Turbacz (1283 m) -> Hala Długa (1210 m) to zejście w dół (-73 m)
    time_downhill = routing.get_edge_travel_time("Schronisko_Turbacz", "Hala_Dluga")

    # Hala Długa (1210 m) -> Turbacz (1283 m) to podejście pod górę (+73 m)
    time_uphill = routing.get_edge_travel_time("Hala_Dluga", "Schronisko_Turbacz")

    # Podejście pod górę w modelu Lorentza MUSI trwać dłużej niż zejście
    assert time_uphill > time_downhill
    assert time_downhill > 0.0


def test_off_trail_terrain_roughness():
    routing = GorceTrailRoutingService()

    # Krawędź na szlaku: Hala Długa -> Polana Gabrowska (on_path=True, eta=1.0)
    time_trail = routing.get_edge_travel_time("Hala_Dluga", "Polana_Gabrowska")

    # Krawędź w trudnym terenie pozaszlakowym: Kudłoń -> Dolina Kamienicy (on_path=False, eta=2.2)
    time_off_trail = routing.get_edge_travel_time("Kudlon", "Dolina_Kamienicy_Wiatrolomy")

    # Czas w wiatrołomach powinien być znacznie wyższy w przeliczeniu na jednostkę dystansu
    edge_trail_dist = routing.graph["Hala_Dluga"]["Polana_Gabrowska"]["distance_3d"]
    edge_off_dist = routing.graph["Kudlon"]["Dolina_Kamienicy_Wiatrolomy"]["distance_3d"]

    pace_trail = time_trail / edge_trail_dist
    pace_off_trail = time_off_trail / edge_off_dist

    assert pace_off_trail > 2.0 * pace_trail


def test_weather_impact_on_gorce_trails():
    good_weather = WeatherConditions()
    bad_weather = WeatherConditions(snow_cm=20.0, wind_kmh=50.0, visibility_m=40.0)

    routing_good = GorceTrailRoutingService(default_weather=good_weather)
    routing_bad = GorceTrailRoutingService(default_weather=bad_weather)

    t_good = routing_good.get_edge_travel_time("Schronisko_Turbacz", "Hala_Dluga")
    t_bad = routing_bad.get_edge_travel_time("Schronisko_Turbacz", "Hala_Dluga")

    assert t_bad > t_good


def test_dijkstra_pathfinding():
    routing = GorceTrailRoutingService()

    # Trasa z Kowańca przez Turbacz na Kiczorę
    path = routing.get_path("Kowaniec_NowyTarg", "Kiczora")
    assert path[0] == "Kowaniec_NowyTarg"
    assert "Schronisko_Turbacz" in path
    assert "Hala_Dluga" in path
    assert "Polana_Gabrowska" in path
    assert path[-1] == "Kiczora"

    total_time = routing.get_total_time("Kowaniec_NowyTarg", "Kiczora")
    assert total_time > 0.0


def test_interactive_map_generation(tmp_path):
    routing = GorceTrailRoutingService()
    output_html = tmp_path / "test_map.html"

    routing.generate_interactive_map(str(output_html))
    assert output_html.is_file()

    content = output_html.read_text(encoding="utf-8")
    assert "leaflet.js" in content
    assert "OpenTopoMap" in content
    assert "Schronisko PTTK Turbacz" in content
