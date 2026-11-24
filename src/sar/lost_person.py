from typing import Any, List, Optional, Union
import networkx as nx
import numpy as np

from src.routing.rescuee import (
    RescueeBehaviorState,
    RescueeRoutingService,
    RescueeState,
    StepResult,
)
from src.routing.routing_interface import AbstractRoutingService
from src.routing.weather_conditions import WeatherConditions


class LostPerson:
    """
    Cienka fasada (adapter) obiektu zaginionego turysty dla modułu SAR / SimPy.
    Deleguje fizykę ruchu, budżet energetyczny Pandolfa i wybór kolejnych węzłów
    do RescueeRoutingService oraz RescueeState z pakietu src.routing.rescuee.
    """

    def __init__(
        self,
        lkp_node: Union[int, str],
        energy: float = 2500.0,
        lost_delay_min: float = 60.0,
        speed_factor: float = 0.6,
        body_mass_kg: float = 75.0,
        load_mass_kg: float = 5.0,
        fatigue_ratio: float = 0.35,
        graph: Optional[nx.DiGraph] = None,
        routing_service: Optional[AbstractRoutingService] = None,
    ):
        self.lost_delay_min = float(lost_delay_min)
        self.state = RescueeState(
            starting_node=lkp_node,
            initial_energy=energy,
            speed_factor=speed_factor,
            body_mass_kg=body_mass_kg,
            load_mass_kg=load_mass_kg,
            fatigue_ratio=fatigue_ratio,
        )
        self._service: Optional[RescueeRoutingService] = (
            RescueeRoutingService(graph_or_path=graph, routing_service=routing_service)
            if (graph is not None or (routing_service is not None and hasattr(routing_service, "graph")))
            else None
        )

    @property
    def current_node(self) -> Union[int, str]:
        return self.state.current_node

    @current_node.setter
    def current_node(self, value: Union[int, str]) -> None:
        self.state.current_node = value

    @property
    def lkp_node(self) -> Union[int, str]:
        return self.state.starting_node

    @property
    def energy(self) -> float:
        return 0.0 if self.state.energy is None else self.state.energy

    @energy.setter
    def energy(self, value: float) -> None:
        self.state.energy = max(0.0, float(value))
        if self.state.energy <= 0.0:
            self.state.is_mobile = False
            self.state.behavior_state = RescueeBehaviorState.IMMOBILIZED

    @property
    def speed_factor(self) -> float:
        return self.state.speed_factor

    @property
    def is_mobile(self) -> bool:
        return self.state.is_mobile

    @is_mobile.setter
    def is_mobile(self, value: bool) -> None:
        self.state.is_mobile = bool(value)

    @property
    def is_found(self) -> bool:
        return self.state.is_found

    @is_found.setter
    def is_found(self, value: bool) -> None:
        self.state.is_found = bool(value)

    @property
    def behavior_state(self) -> RescueeBehaviorState:
        return self.state.behavior_state

    @property
    def path_history(self) -> List[Union[int, str]]:
        return self.state.path_history

    def _get_service(
        self,
        graph: Optional[nx.DiGraph] = None,
        routing_service: Optional[AbstractRoutingService] = None,
    ) -> RescueeRoutingService:
        if graph is not None or routing_service is not None:
            return RescueeRoutingService(graph_or_path=graph, routing_service=routing_service)
        if self._service is not None:
            return self._service
        raise ValueError("Wymagany jest graf terenu (graph) lub serwis trasowania z atrybutem .graph.")

    def choose_next_node(
        self,
        graph: Optional[nx.DiGraph] = None,
        weather: Optional[WeatherConditions] = None,
        rng: Optional[np.random.Generator] = None,
    ) -> Optional[Union[int, str]]:
        """Wybiera kolejny węzeł na podstawie topografii, energii i pogody."""
        service = self._get_service(graph=graph)
        return service.choose_next_node(self.state, weather=weather, rng=rng)

    def simulate_pre_report_movement(
        self,
        delay_min: Optional[float] = None,
        graph: Optional[nx.DiGraph] = None,
        routing_service: Optional[AbstractRoutingService] = None,
        weather: Optional[WeatherConditions] = None,
        rng: Optional[np.random.Generator] = None,
    ) -> List[StepResult]:
        """Symuluje przemieszczanie się zaginionego przed przyjęciem zgłoszenia."""
        effective_delay = self.lost_delay_min if delay_min is None else delay_min
        service = self._get_service(graph=graph, routing_service=routing_service)
        return service.simulate_pre_report_movement(
            self.state,
            delay_min=effective_delay,
            weather=weather,
            rng=rng,
        )

    def wander_process(
        self,
        env: Any,
        graph: Optional[nx.DiGraph] = None,
        routing_service: Optional[AbstractRoutingService] = None,
        weather: Optional[WeatherConditions] = None,
        rng: Optional[np.random.Generator] = None,
    ):
        """Proces SimPy równoległego błądzenia zaginionego podczas trwania akcji."""
        service = self._get_service(graph=graph, routing_service=routing_service)
        return (yield from service.wander_process(env, self.state, weather=weather, rng=rng))
