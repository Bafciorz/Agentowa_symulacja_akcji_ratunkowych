import math
import pytest
import networkx as nx

from src.routing import (
    WeatherConditions,
    AbstractRoutingService,
    MockRoutingService,
    TerrainRoutingService
)


def test_weather_conditions_modifier():
    # Idealne warunki
    w_ideal = WeatherConditions()
    assert w_ideal.env_modifier == 1.0

    # Lekki deszcz
    w_light_rain = WeatherConditions(rain_mm_h=5.0)
    assert abs(w_light_rain.env_modifier - 0.92) < 1e-4

    # Ulewa
    w_heavy_rain = WeatherConditions(rain_mm_h=20.0)
    assert abs(w_heavy_rain.env_modifier - 0.65) < 1e-4

    # Śnieg 20 cm
    w_snow = WeatherConditions(snow_cm=20.0)
    assert abs(w_snow.env_modifier - 0.50) < 1e-4

    # Głęboki śnieg (> 30 cm)
    w_deep_snow = WeatherConditions(snow_cm=45.0)
    assert abs(w_deep_snow.env_modifier - 0.30) < 1e-4

    # Wichura (> 70 km/h)
    w_storm = WeatherConditions(wind_kmh=80.0)
    assert abs(w_storm.env_modifier - 0.50) < 1e-4

    # Mgła (< 50 m)
    w_fog = WeatherConditions(visibility_m=30.0)
    assert abs(w_fog.env_modifier - 0.75) < 1e-4


def test_get_edge_travel_time_adjacent_nodes_validation():
    # Budujemy mały graf testowy: A -> B -> C (A i C NIE leżą obok siebie)
    G = nx.DiGraph()
    G.add_node("A", x_metric=0.0, y_metric=0.0, z=800.0)
    G.add_node("B", x_metric=100.0, y_metric=0.0, z=800.0)
    G.add_node("C", x_metric=200.0, y_metric=0.0, z=800.0)

    G.add_edge("A", "B", distance_2d=100.0, elevation_change=0.0, distance_3d=100.0)
    G.add_edge("B", "C", distance_2d=100.0, elevation_change=0.0, distance_3d=100.0)

    routing = TerrainRoutingService(G)

    # 1. Krawędź bezpośrednia (A -> B) - działa poprawnie
    time_ab = routing.get_edge_travel_time("A", "B")
    assert time_ab > 0.0

    # 2. Węzły nie leżące obok siebie (A -> C) - rzuca ValueError
    with pytest.raises(ValueError, match="nie leżą obok siebie"):
        routing.get_edge_travel_time("A", "C")

    # 3. Krawędź w przeciwnym kierunku (B -> A) nie istnieje w grafie skierowanym - rzuca ValueError
    with pytest.raises(ValueError, match="nie leżą obok siebie"):
        routing.get_edge_travel_time("B", "A")

    # 4. Węzeł nieistniejący - rzuca KeyError
    with pytest.raises(KeyError):
        routing.get_edge_travel_time("A", "NON_EXISTING")


def test_get_edge_travel_time_physics_and_math():
    G = nx.DiGraph()
    G.add_node("Start", x_metric=0.0, y_metric=0.0, z=800.0)
    G.add_node("Flat", x_metric=100.0, y_metric=0.0, z=800.0)
    G.add_node("Uphill", x_metric=100.0, y_metric=100.0, z=830.0)      # 30m podejścia na 141m
    G.add_node("SteepUp", x_metric=0.0, y_metric=100.0, z=850.0)       # 50m podejścia na 100m (S=0.5 > 0.27)
    G.add_node("Downhill", x_metric=100.0, y_metric=-100.0, z=780.0)   # 20m w dół na 141m

    G.add_edge("Start", "Flat", distance_2d=100.0, elevation_change=0.0, distance_3d=100.0)
    G.add_edge("Start", "Uphill", distance_2d=141.42, elevation_change=30.0, distance_3d=144.57)
    G.add_edge("Start", "SteepUp", distance_2d=100.0, elevation_change=50.0, distance_3d=111.80)
    G.add_edge("Start", "Downhill", distance_2d=141.42, elevation_change=-20.0, distance_3d=142.83)

    routing = TerrainRoutingService(G)

    # 1. Teren płaski: v_base na płaskim to ok. 1.33 m/s -> 100m / 1.33 = ~75s = ~1.25 min
    t_flat = routing.get_edge_travel_time("Start", "Flat")
    assert abs(t_flat - 1.25) < 0.1

    # 2. Podejście pod górę trwa dłużej na metr niż marsz po płaskim
    t_uphill = routing.get_edge_travel_time("Start", "Uphill")
    speed_flat = 100.0 / (t_flat * 60.0)
    speed_uphill = 144.57 / (t_uphill * 60.0)
    assert speed_uphill < speed_flat

    # 3. Wpływ zejścia ze szlaku i szorstkości podłoża (on_path=False, eta=1.5)
    t_flat_on_path = routing.get_edge_travel_time("Start", "Flat", on_path=True)
    t_flat_off_path = routing.get_edge_travel_time("Start", "Flat", on_path=False, eta_roughness=1.5)
    assert t_flat_off_path > t_flat_on_path

    # 4. Wpływ pogody (śnieg i mgła)
    bad_weather = WeatherConditions(snow_cm=20.0, visibility_m=30.0)
    t_bad_weather = routing.get_edge_travel_time("Start", "Flat", weather=bad_weather)
    assert t_bad_weather > t_flat_on_path


def test_empty_methods_stubs():
    G = nx.DiGraph()
    G.add_edge("A", "B", distance_2d=100.0, elevation_change=0.0)
    routing = TerrainRoutingService(G)

    # get_path i get_total_time są obecnie puste (zgodnie z poleceniem)
    assert routing.get_path("A", "B") is None
    assert routing.get_total_time("A", "B") is None
