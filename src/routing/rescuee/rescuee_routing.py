from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Union
import networkx as nx
import numpy as np

from src.routing.routing_interface import AbstractRoutingService
from src.routing.rescuer import TerrainRoutingService
from src.routing.weather_conditions import WeatherConditions
from src.routing.rescuee.energy_model import AbstractEnergyModel, PandolfEnergyModel
from src.routing.rescuee.movement_policy import (
    AbstractMovementPolicy,
    TerrainEnergyMovementPolicy,
    extract_edge_geometry,
)
from src.routing.rescuee.rescuee_state import (
    RescueeBehaviorState,
    RescueeState,
    StepResult,
)

if TYPE_CHECKING:
    import simpy


@dataclass(frozen=True)
class _PlannedStep:
    """Wewnętrzny plan kroku współdzielony przez step() oraz wander_process()."""
    from_node: Union[int, str]
    to_node: Union[int, str]
    action: str
    new_state: RescueeBehaviorState
    travel_time_min: float
    energy_spent_kj: float


class RescueeRoutingService:
    """
    Serwis ruchu i budżetu energetycznego osoby zaginionej (rescuee) na grafie terenu.

    Zaprojektowany analogicznie do TerrainRoutingService (SOLID + KISS):
    - Współpracuje z dowolnym grafem DEM lub grafem szlaków Gorców (nx.DiGraph / GraphML),
    - Deleguje czas pokonania pojedynczej krawędzi do wstrzykniętego AbstractRoutingService,
    - Naliczanie zużycia energii realizuje przez AbstractEnergyModel (domyślnie Pandolf 1977),
    - Wybór kolejnego węzła deleguje do AbstractMovementPolicy (teren, nachylenie, zmęczenie).
    """

    def __init__(
        self,
        graph_or_path: Optional[Union[nx.DiGraph, str, Path]] = None,
        routing_service: Optional[AbstractRoutingService] = None,
        energy_model: Optional[AbstractEnergyModel] = None,
        movement_policy: Optional[AbstractMovementPolicy] = None,
        default_weather: Optional[WeatherConditions] = None,
        rest_step_min: float = 15.0,
    ):
        self.graph: nx.DiGraph = self._resolve_graph(graph_or_path, routing_service)
        self.routing_service: AbstractRoutingService = (
            routing_service if routing_service is not None else TerrainRoutingService(self.graph)
        )
        self.energy_model: AbstractEnergyModel = (
            energy_model if energy_model is not None else PandolfEnergyModel()
        )
        self.movement_policy: AbstractMovementPolicy = (
            movement_policy if movement_policy is not None else TerrainEnergyMovementPolicy()
        )
        self.default_weather: WeatherConditions = (
            default_weather if default_weather is not None else WeatherConditions()
        )
        self.rest_step_min = max(float(rest_step_min), 1.0)

    @staticmethod
    def _resolve_graph(
        graph_or_path: Optional[Union[nx.DiGraph, str, Path]],
        routing_service: Optional[AbstractRoutingService],
    ) -> nx.DiGraph:
        if graph_or_path is None and routing_service is not None and hasattr(routing_service, "graph"):
            return routing_service.graph
        if isinstance(graph_or_path, (str, Path)):
            from data.mappers.terrain_mapper import TerrainGraphMapper

            return TerrainGraphMapper().load_graph(str(graph_or_path))
        if isinstance(graph_or_path, nx.DiGraph):
            return graph_or_path
        raise TypeError(
            "Oczekiwano nx.DiGraph, ścieżki do pliku GraphML lub routing_service z atrybutem .graph."
        )

    def create_rescuee(
        self,
        starting_node: Union[int, str],
        initial_energy: float = 2500.0,
        speed_factor: float = 0.6,
        body_mass_kg: float = 75.0,
        load_mass_kg: float = 5.0,
        fatigue_ratio: float = 0.35,
    ) -> RescueeState:
        """
        Tworzy obiekt stanu zaginionego w zadanym węźle startowym z początkową energią.
        """
        if starting_node not in self.graph:
            raise KeyError(f"Węzeł startowy '{starting_node}' nie istnieje w grafie terenu.")

        return RescueeState(
            starting_node=starting_node,
            initial_energy=initial_energy,
            speed_factor=speed_factor,
            body_mass_kg=body_mass_kg,
            load_mass_kg=load_mass_kg,
            fatigue_ratio=fatigue_ratio,
        )

    def choose_next_node(
        self,
        state: RescueeState,
        weather: Optional[WeatherConditions] = None,
        rng: Optional[np.random.Generator] = None,
    ) -> Optional[Union[int, str]]:
        """
        Zwraca wybrany następny węzeł sąsiedni lub None (postój / brak sił).
        """
        active_weather = weather if weather is not None else self.default_weather
        active_rng = rng if rng is not None else np.random.default_rng()
        decision = self.movement_policy.decide_next_step(
            self.graph, state, active_weather, active_rng
        )
        return decision.next_node

    def step(
        self,
        state: RescueeState,
        weather: Optional[WeatherConditions] = None,
        rng: Optional[np.random.Generator] = None,
    ) -> StepResult:
        """
        Wykonuje jeden krok czasoprzestrzenny zaginionego i aktualizuje jego stan oraz energię.
        """
        active_weather = weather if weather is not None else self.default_weather
        active_rng = rng if rng is not None else np.random.default_rng()

        planned = self._plan_step(state, active_weather, active_rng)
        return self._commit_step(state, planned)

    def simulate_pre_report_movement(
        self,
        state: RescueeState,
        delay_min: float,
        weather: Optional[WeatherConditions] = None,
        rng: Optional[np.random.Generator] = None,
    ) -> List[StepResult]:
        """
        Symuluje przemieszczanie się zaginionego przed zgłoszeniem (delay_min od zagubienia).
        """
        if delay_min <= 0.0:
            return []

        active_weather = weather if weather is not None else self.default_weather
        active_rng = rng if rng is not None else np.random.default_rng()

        history: List[StepResult] = []
        elapsed = 0.0

        while elapsed < delay_min and state.is_mobile and not state.is_found:
            result = self.step(state, weather=active_weather, rng=active_rng)
            history.append(result)
            if result.action == "IMMOBILIZED" or result.travel_time_min <= 0.0:
                break
            elapsed += result.travel_time_min

        return history

    def wander_process(
        self,
        env: "simpy.Environment",
        state: RescueeState,
        weather: Optional[WeatherConditions] = None,
        rng: Optional[np.random.Generator] = None,
    ):
        """
        Proces SimPy symulujący bieżący ruch zaginionego podczas trwania akcji ratunkowej.
        Zatrzymuje się po odnalezieniu (is_found = True) lub wyczerpaniu energii (is_mobile = False).
        """
        active_weather = weather if weather is not None else self.default_weather
        active_rng = rng if rng is not None else np.random.default_rng()

        while state.is_mobile and not state.is_found:
            planned = self._plan_step(state, active_weather, active_rng)
            if planned.action == "IMMOBILIZED":
                self._commit_step(state, planned)
                break

            if planned.travel_time_min > 0.0:
                yield env.timeout(planned.travel_time_min)

            if state.is_found:
                break

            self._commit_step(state, planned)

    def _plan_step(
        self,
        state: RescueeState,
        weather: WeatherConditions,
        rng: np.random.Generator,
    ) -> _PlannedStep:
        curr = state.current_node
        if state.is_found or not state.is_mobile or (state.energy is not None and state.energy <= 0.0):
            return _PlannedStep(
                from_node=curr,
                to_node=curr,
                action="IMMOBILIZED",
                new_state=RescueeBehaviorState.IMMOBILIZED,
                travel_time_min=0.0,
                energy_spent_kj=0.0,
            )

        decision = self.movement_policy.decide_next_step(self.graph, state, weather, rng)

        if decision.next_node is None:
            if decision.new_state == RescueeBehaviorState.IMMOBILIZED:
                return _PlannedStep(
                    from_node=curr,
                    to_node=curr,
                    action="IMMOBILIZED",
                    new_state=RescueeBehaviorState.IMMOBILIZED,
                    travel_time_min=0.0,
                    energy_spent_kj=0.0,
                )

            rest_energy = self.energy_model.calculate_rest_energy(self.rest_step_min, weather)
            return _PlannedStep(
                from_node=curr,
                to_node=curr,
                action="STAY_PUT",
                new_state=RescueeBehaviorState.STAYING_PUT,
                travel_time_min=self.rest_step_min,
                energy_spent_kj=rest_energy,
            )

        next_node = decision.next_node
        geom = extract_edge_geometry(self.graph, curr, next_node)

        travel_time_min = self.routing_service.get_edge_travel_time(
            curr,
            next_node,
            on_path=geom.on_path,
            eta_roughness=geom.eta_roughness,
            weather=weather,
            speed_factor=state.speed_factor,
        )

        move_energy = self.energy_model.calculate_move_energy(
            dist_2d_m=geom.dist_2d_m,
            dist_3d_m=geom.dist_3d_m,
            delta_h_m=geom.delta_h_m,
            travel_time_min=travel_time_min,
            body_mass_kg=state.body_mass_kg,
            load_mass_kg=state.load_mass_kg,
            eta_roughness=geom.eta_roughness,
        )

        return _PlannedStep(
            from_node=curr,
            to_node=next_node,
            action="MOVE",
            new_state=decision.new_state,
            travel_time_min=travel_time_min,
            energy_spent_kj=move_energy,
        )

    @staticmethod
    def _commit_step(state: RescueeState, planned: _PlannedStep) -> StepResult:
        current_energy = 0.0 if state.energy is None else state.energy
        new_energy = max(0.0, current_energy - planned.energy_spent_kj)
        state.energy = new_energy
        state.elapsed_time_min += planned.travel_time_min

        if planned.action == "MOVE":
            state.prev_node = planned.from_node
            state.current_node = planned.to_node
            state.path_history.append(planned.to_node)

        if planned.action == "IMMOBILIZED" or new_energy <= 0.0:
            state.is_mobile = False
            state.behavior_state = RescueeBehaviorState.IMMOBILIZED
        else:
            state.behavior_state = planned.new_state

        return StepResult(
            from_node=planned.from_node,
            to_node=planned.to_node,
            action=planned.action,
            behavior_state=state.behavior_state,
            travel_time_min=planned.travel_time_min,
            energy_spent_kj=planned.energy_spent_kj,
            remaining_energy_kj=new_energy,
        )
