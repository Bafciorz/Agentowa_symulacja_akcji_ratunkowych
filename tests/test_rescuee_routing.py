import networkx as nx
import numpy as np
import pytest
import simpy

from src.routing import (
    GorceTrailRoutingService,
    PandolfEnergyModel,
    RescueeBehaviorState,
    RescueeRoutingService,
    RescueeState,
    TerrainRoutingService,
    WeatherConditions,
    build_gorce_trails_graph,
)
from src.sar import LostPerson


def _build_dem_slope_graph() -> nx.DiGraph:
    """Buduje testowy graf DEM ze szczytem, doliną i granią (węzły sąsiadujące)."""
    G = nx.DiGraph()
    G.add_node("Peak", x_metric=500.0, y_metric=500.0, z=1200.0)
    G.add_node("Valley", x_metric=500.0, y_metric=300.0, z=1050.0)
    G.add_node("Ridge", x_metric=700.0, y_metric=500.0, z=1200.0)
    G.add_node("UpperPeak", x_metric=500.0, y_metric=700.0, z=1320.0)
    G.add_node("LowerBasin", x_metric=500.0, y_metric=100.0, z=900.0)

    def link(u: str, v: str, on_path: bool = False, eta: float = 1.2) -> None:
        du = G.nodes[u]
        dv = G.nodes[v]
        d2 = float(np.hypot(dv["x_metric"] - du["x_metric"], dv["y_metric"] - du["y_metric"]))
        dz = dv["z"] - du["z"]
        d3 = float(np.hypot(d2, dz))
        G.add_edge(
            u,
            v,
            distance_2d=d2,
            distance_3d=d3,
            elevation_change=dz,
            on_path=on_path,
            eta_roughness=eta,
        )

    for a, b in [
        ("Peak", "Valley"),
        ("Peak", "Ridge"),
        ("Peak", "UpperPeak"),
        ("Valley", "LowerBasin"),
        ("Ridge", "Valley"),
    ]:
        link(a, b)
        link(b, a)

    return G


def test_pandolf_energy_model_physics():
    model = PandolfEnergyModel()

    # Ten sam dystans poziomy 500 m w 10 min -> podejście musi kosztować więcej energii niż płaski i zejście
    e_up = model.calculate_move_energy(
        dist_2d_m=500.0,
        dist_3d_m=522.0,
        delta_h_m=150.0,
        travel_time_min=10.0,
        body_mass_kg=75.0,
        load_mass_kg=5.0,
        eta_roughness=1.0,
    )
    e_flat = model.calculate_move_energy(
        dist_2d_m=500.0,
        dist_3d_m=500.0,
        delta_h_m=0.0,
        travel_time_min=10.0,
        body_mass_kg=75.0,
        load_mass_kg=5.0,
        eta_roughness=1.0,
    )
    e_down = model.calculate_move_energy(
        dist_2d_m=500.0,
        dist_3d_m=522.0,
        delta_h_m=-150.0,
        travel_time_min=10.0,
        body_mass_kg=75.0,
        load_mass_kg=5.0,
        eta_roughness=1.0,
    )
    e_rough = model.calculate_move_energy(
        dist_2d_m=500.0,
        dist_3d_m=500.0,
        delta_h_m=0.0,
        travel_time_min=10.0,
        body_mass_kg=75.0,
        load_mass_kg=5.0,
        eta_roughness=2.0,
    )

    assert e_up > e_flat >= e_down * 0.9
    assert e_rough > e_flat

    # Spoczynek w zimie drenuje energię szybciej niż w pogodzie bezśnieżnej
    e_rest_mild = model.calculate_rest_energy(15.0, WeatherConditions())
    e_rest_winter = model.calculate_rest_energy(15.0, WeatherConditions(snow_cm=25.0, wind_kmh=60.0))
    assert e_rest_mild == pytest.approx(90.0)  # 100 W * 900 s / 1000 = 90 kJ
    assert e_rest_winter > e_rest_mild


def test_rescuee_state_validation_and_immobilization():
    state_zero = RescueeState(starting_node="Peak", initial_energy=0.0)
    assert state_zero.is_mobile is False
    assert state_zero.behavior_state == RescueeBehaviorState.IMMOBILIZED
    assert state_zero.lkp_node == "Peak"

    with pytest.raises(ValueError):
        RescueeState(starting_node="Peak", initial_energy=-10.0)
    with pytest.raises(ValueError):
        RescueeState(starting_node="Peak", speed_factor=0.0)


def test_rescuee_step_and_energy_exhaustion():
    G = _build_dem_slope_graph()
    service = RescueeRoutingService(G)
    rng = np.random.default_rng(42)

    # Mała energia początkowa -> po kilku krokach powinna spaść do 0 i zatrzymać agenta
    state = service.create_rescuee(starting_node="Peak", initial_energy=180.0, speed_factor=0.6)

    steps = []
    for _ in range(15):
        res = service.step(state, rng=rng)
        steps.append(res)
        if not state.is_mobile:
            break

    assert state.energy == 0.0
    assert state.is_mobile is False
    assert state.behavior_state == RescueeBehaviorState.IMMOBILIZED

    # Kolejny krok po wyczerpaniu energii nie przesuwa ani nie zużywa czasu
    after = service.step(state, rng=rng)
    assert after.action == "IMMOBILIZED"
    assert after.travel_time_min == 0.0
    assert after.from_node == after.to_node == state.current_node

    # Wszystkie odwiedzone krawędzie muszą istnieć w grafie
    for u, v in zip(state.path_history[:-1], state.path_history[1:]):
        assert G.has_edge(u, v)


def test_fatigued_rescuee_prefers_descending_slope():
    G = _build_dem_slope_graph()
    service = RescueeRoutingService(G)
    rng = np.random.default_rng(123)

    downhill_count = 0
    uphill_count = 0
    trials = 200

    for _ in range(trials):
        # Energia poniżej progu zmęczenia (20% < 35%) -> tryb schodzenia do doliny
        state = service.create_rescuee(starting_node="Peak", initial_energy=1000.0)
        state.energy = 200.0
        next_node = service.choose_next_node(state, rng=rng)
        if next_node is not None:
            z_curr = G.nodes["Peak"]["z"]
            z_next = G.nodes[next_node]["z"]
            if z_next < z_curr:
                downhill_count += 1
            elif z_next > z_curr:
                uphill_count += 1

    assert downhill_count > uphill_count * 3


def test_pre_report_movement_and_gorce_trails_integration():
    gorce_routing = GorceTrailRoutingService()
    service = RescueeRoutingService(
        graph_or_path=build_gorce_trails_graph(),
        routing_service=gorce_routing,
    )
    rng = np.random.default_rng(7)

    state = service.create_rescuee(starting_node="Schronisko_Turbacz", initial_energy=3000.0)
    history = service.simulate_pre_report_movement(state, delay_min=90.0, rng=rng)

    assert len(history) >= 1
    assert state.elapsed_time_min >= 90.0 or not state.is_mobile
    assert state.energy < 3000.0
    assert state.path_history[0] == "Schronisko_Turbacz"


def test_simpy_wander_process_stops_when_found():
    G = _build_dem_slope_graph()
    env = simpy.Environment()
    routing = TerrainRoutingService(G)

    lost = LostPerson(
        lkp_node="Peak",
        energy=5000.0,
        speed_factor=0.6,
        graph=G,
        routing_service=routing,
    )
    rng = np.random.default_rng(99)

    proc = env.process(lost.wander_process(env, rng=rng))

    def rescue_finder():
        yield env.timeout(30.0)
        lost.is_found = True

    env.process(rescue_finder())
    env.run(until=120.0)

    assert lost.is_found is True
    assert not proc.is_alive
    assert lost.energy < 5000.0
