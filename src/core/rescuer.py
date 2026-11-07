import enum
from typing import Union

import simpy

from src.core.incident import Incident


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
        routing_service,
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
