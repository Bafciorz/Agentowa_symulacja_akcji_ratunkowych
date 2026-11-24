import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple, Union
import networkx as nx
import numpy as np

from src.routing.rescuee.rescuee_state import RescueeBehaviorState, RescueeState
from src.routing.weather_conditions import WeatherConditions


@dataclass(frozen=True)
class EdgeGeometry:
    """Parametry fizyczne pojedynczej krawędzi grafu (u -> v)."""
    dist_2d_m: float
    dist_3d_m: float
    delta_h_m: float
    on_path: bool
    eta_roughness: float


def extract_edge_geometry(
    graph: nx.DiGraph,
    u: Union[int, str],
    v: Union[int, str],
) -> EdgeGeometry:
    """Pobiera lub wylicza parametry geometryczne i terenowe krawędzi u -> v."""
    edge_data = graph.get_edge_data(u, v) or {}
    u_node = graph.nodes[u]
    v_node = graph.nodes[v]

    if "distance_2d" in edge_data:
        dist_2d = float(edge_data["distance_2d"])
    elif "x_metric" in u_node and "x_metric" in v_node:
        dist_2d = math.hypot(
            float(v_node["x_metric"]) - float(u_node["x_metric"]),
            float(v_node["y_metric"]) - float(u_node["y_metric"]),
        )
    elif "lon" in u_node and "lon" in v_node:
        dist_2d = math.hypot(
            (float(v_node["lon"]) - float(u_node["lon"])) * 72200.0,
            (float(v_node["lat"]) - float(u_node["lat"])) * 111200.0,
        )
    else:
        dist_2d = math.hypot(
            float(v_node.get("x", 0.0)) - float(u_node.get("x", 0.0)),
            float(v_node.get("y", 0.0)) - float(u_node.get("y", 0.0)),
        )

    if "elevation_change" in edge_data:
        delta_h = float(edge_data["elevation_change"])
    else:
        delta_h = float(v_node.get("z", 0.0)) - float(u_node.get("z", 0.0))

    if "distance_3d" in edge_data:
        dist_3d = float(edge_data["distance_3d"])
    else:
        dist_3d = math.hypot(max(dist_2d, 1e-6), delta_h)

    on_path = bool(edge_data.get("on_path", True))
    eta_roughness = float(edge_data.get("eta_roughness", edge_data.get("eta", 1.0)))

    return EdgeGeometry(
        dist_2d_m=max(dist_2d, 1e-6),
        dist_3d_m=max(dist_3d, 1e-6),
        delta_h_m=delta_h,
        on_path=on_path,
        eta_roughness=max(eta_roughness, 1.0),
    )


@dataclass(frozen=True)
class MovementDecision:
    """Decyzja o kolejnym kroku zaginionego: węzeł docelowy (lub None) i nowy stan."""
    next_node: Optional[Union[int, str]]
    new_state: RescueeBehaviorState


class AbstractMovementPolicy(ABC):
    """Kontrakt polityki wyboru kolejnego węzła przez osobę zaginioną."""

    @abstractmethod
    def decide_next_step(
        self,
        graph: nx.DiGraph,
        state: RescueeState,
        weather: WeatherConditions,
        rng: np.random.Generator,
    ) -> MovementDecision:
        """Zwraca decyzję ruchu na podstawie topografii, energii i pogody."""
        pass


class TerrainEnergyMovementPolicy(AbstractMovementPolicy):
    """
    Polityka ruchu zaginionego łącząca:
    - Correlated Random Walk (bezwładność kierunku + kara za strome zbocza z kompendium WiSAR),
    - Spadek energii i przejście w preferencję schodzenia w dół dolin (Sprint 1: 55-60% dół, 25-30% grań/płasko),
    - Szansę zatrzymania się / przeczekania (STAYING_PUT) rosnącą wraz ze zmęczeniem i pogorszeniem pogody.
    """

    def __init__(
        self,
        base_stay_prob: float = 0.10,
        max_stay_prob: float = 0.45,
        trail_loss_base_prob: float = 0.05,
        direction_inertia_coeff: float = 1.5,
        steepness_penalty_coeff: float = 3.0,
    ):
        self.base_stay_prob = base_stay_prob
        self.max_stay_prob = max_stay_prob
        self.trail_loss_base_prob = trail_loss_base_prob
        self.direction_inertia_coeff = direction_inertia_coeff
        self.steepness_penalty_coeff = steepness_penalty_coeff

    def decide_next_step(
        self,
        graph: nx.DiGraph,
        state: RescueeState,
        weather: WeatherConditions,
        rng: np.random.Generator,
    ) -> MovementDecision:
        if not state.is_mobile or (state.energy is not None and state.energy <= 0.0):
            return MovementDecision(None, RescueeBehaviorState.IMMOBILIZED)

        neighbors = list(graph.neighbors(state.current_node))
        if not neighbors:
            return MovementDecision(None, RescueeBehaviorState.IMMOBILIZED)

        # 1. Sprawdzenie czy zaginiony robi postój (STAYING_PUT)
        stay_prob = self._compute_stay_probability(state, weather)
        if rng.random() < stay_prob:
            return MovementDecision(None, RescueeBehaviorState.STAYING_PUT)

        # 2. Określenie trybu przemieszczania się (maszyna stanów)
        mode = self._determine_movement_mode(graph, state, neighbors, weather, rng)

        # 3. Wyliczenie wag prawdopodobieństwa dla sąsiadów
        weights = []
        for neighbor in neighbors:
            geom = extract_edge_geometry(graph, state.current_node, neighbor)
            slope_s = geom.delta_h_m / max(geom.dist_2d_m, 1e-6)

            dir_w = self._direction_weight(graph, state.prev_node, state.current_node, neighbor)
            steep_w = math.exp(-self.steepness_penalty_coeff * abs(slope_s))
            mode_w = self._terrain_mode_weight(geom.delta_h_m, geom.on_path, mode)

            weights.append(max(dir_w * steep_w * mode_w, 1e-9))

        probs = np.array(weights, dtype=float)
        probs /= probs.sum()

        chosen_idx = int(rng.choice(len(neighbors), p=probs))
        return MovementDecision(next_node=neighbors[chosen_idx], new_state=mode)

    def _compute_stay_probability(
        self,
        state: RescueeState,
        weather: WeatherConditions,
    ) -> float:
        fatigue_bonus = 0.15 * (1.0 - state.energy_ratio)
        weather_bonus = 0.0
        if weather.snow_cm > 15.0:
            weather_bonus += 0.08
        if weather.wind_kmh > 50.0:
            weather_bonus += 0.07
        if weather.visibility_m < 50.0:
            weather_bonus += 0.05

        return min(self.max_stay_prob, max(0.0, self.base_stay_prob + fatigue_bonus + weather_bonus))

    def _determine_movement_mode(
        self,
        graph: nx.DiGraph,
        state: RescueeState,
        neighbors: list,
        weather: WeatherConditions,
        rng: np.random.Generator,
    ) -> RescueeBehaviorState:
        if state.is_fatigued:
            return RescueeBehaviorState.DRAINAGE_FOLLOWING

        has_trail_edge = any(
            bool((graph.get_edge_data(state.current_node, n) or {}).get("on_path", True))
            for n in neighbors
        )
        if not has_trail_edge or state.behavior_state == RescueeBehaviorState.OFF_PATH_WANDERING:
            return RescueeBehaviorState.OFF_PATH_WANDERING

        p_lose_trail = self.trail_loss_base_prob
        if weather.visibility_m < 50.0:
            p_lose_trail += 0.35
        if weather.snow_cm > 10.0:
            p_lose_trail += 0.25

        if rng.random() < min(p_lose_trail, 0.85):
            return RescueeBehaviorState.OFF_PATH_WANDERING

        return RescueeBehaviorState.ROUTE_TRAVELING

    def _direction_weight(
        self,
        graph: nx.DiGraph,
        prev_node: Optional[Union[int, str]],
        curr_node: Union[int, str],
        cand_node: Union[int, str],
    ) -> float:
        if prev_node is None:
            return 1.0

        p_xy = self._node_xy(graph, prev_node)
        c_xy = self._node_xy(graph, curr_node)
        n_xy = self._node_xy(graph, cand_node)

        if p_xy is None or c_xy is None or n_xy is None:
            return 0.1 if cand_node == prev_node else 1.0

        v1x, v1y = c_xy[0] - p_xy[0], c_xy[1] - p_xy[1]
        v2x, v2y = n_xy[0] - c_xy[0], n_xy[1] - c_xy[1]

        norm1 = math.hypot(v1x, v1y)
        norm2 = math.hypot(v2x, v2y)
        if norm1 < 1e-6 or norm2 < 1e-6:
            return 0.1 if cand_node == prev_node else 1.0

        cos_theta = max(-1.0, min(1.0, (v1x * v2x + v1y * v2y) / (norm1 * norm2)))
        delta_psi = math.acos(cos_theta)
        return math.exp(-self.direction_inertia_coeff * abs(delta_psi))

    @staticmethod
    def _node_xy(graph: nx.DiGraph, node_id: Union[int, str]) -> Optional[Tuple[float, float]]:
        data = graph.nodes[node_id]
        if "x_metric" in data and "y_metric" in data:
            return float(data["x_metric"]), float(data["y_metric"])
        if "lon" in data and "lat" in data:
            return float(data["lon"]) * 72200.0, float(data["lat"]) * 111200.0
        if "x" in data and "y" in data:
            return float(data["x"]), float(data["y"])
        return None

    @staticmethod
    def _terrain_mode_weight(
        delta_h_m: float,
        on_path: bool,
        mode: RescueeBehaviorState,
    ) -> float:
        if mode == RescueeBehaviorState.DRAINAGE_FOLLOWING:
            # Silna preferencja schodzenia w dół (55-60%), umiarkowana dla płaskiego (25-30%)
            if delta_h_m < -1.0:
                return 3.0
            if abs(delta_h_m) <= 1.0:
                return 1.4
            return 0.3

        if mode == RescueeBehaviorState.OFF_PATH_WANDERING:
            if delta_h_m < -1.0:
                return 1.8
            if abs(delta_h_m) <= 1.0:
                return 1.2
            return 0.5

        # ROUTE_TRAVELING
        trail_factor = 2.5 if on_path else 0.35
        elev_factor = 1.25 if delta_h_m <= 1.0 else 0.75
        return trail_factor * elev_factor
