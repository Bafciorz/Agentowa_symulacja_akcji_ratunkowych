import enum
from typing import Union

import simpy

from src.core.incident import Incident
from src.routing.routing_interface import AbstractRoutingService


class RescuerState(enum.Enum):
    IDLE = "IDLE" #czeka w bazie na wezwanie
    MOBILIZING = "MOBILIZING" #ubieranie sie itd
    EN_ROUTE = "EN_ROUTE" #idzie szlakiem do wypadku
    ON_SCENE = "ON_SCENE" #udziela pomocy
    RETURNING = "RETURNING" #wraca z akcji
    SEARCHING = "SEARCHING" #jest w trakcie poszukiwan

class Rescuer:
    def __init__(
        self,
        env: simpy.Environment,
        agent_id: str,
        base_node: Union[int, str],
        routing_service: AbstractRoutingService,
        speed_factor: float = 1.0,
        is_volunteer: bool = False
    ):
        self.env = env
        self.agent_id = agent_id
        self.base_node = base_node
        self.current_node = base_node
        self.routing_service = routing_service
        self.speed_factor = speed_factor
        self.is_volunteer = is_volunteer

        self.state: RescuerState = RescuerState.IDLE
        self.current_incident: Incident | None = None
        self.process: simpy.Process | None = None

    def assingn_incident (self, incident: Incident) -> simpy.Process:
        self.current_incident = incident
        self.process = self.env.process(self._mission_lifecycle())
        return self.process

    def _travel_to(self, destination):
        path = self.routing_service.get_path(self.current_node, destination)

        if len(path) <= 1:
            return True
        for i in range(len(path) - 1):
            u = path[i]
            v = path[i + 1]

            t_edge = self.routing_service.get_edge_travel_time(u, v, self.speed_factor)
            yield self.env.timeout(t_edge)
            self.current_node = v
        return True