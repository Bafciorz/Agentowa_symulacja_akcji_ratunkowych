import enum
from typing import Union, Any, Generator

import simpy
from simpy import Timeout

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

    def assign_incident (self, incident: Incident) -> simpy.Process:
        """
        przypisanie incydentu
        :param incident:
        :return: simpy.Process
        """
        self.current_incident = incident
        self.process = self.env.process(self._mission_lifecycle())
        return self.process

    def _travel_to(self, destination) -> Generator[Timeout, Any, bool]:
        """
        pojedynczy krok
        :param destination:
        :return: bool
        """
        path = self.routing_service.get_path(self.current_node, destination)
        if len(path) <= 1:
            return True
        for i in range(len(path) - 1):
            u = path[i]
            v = path[i + 1]
            t_edge = self.routing_service.get_edge_travel_time(u, v, self.speed_factor)
            try:
                yield self.env.timeout(t_edge)
                self.current_node = v
            except simpy.Interrupt as inter:
                self.current_node = v
                print(f"[{self.env.now:.1f} min] {self.agent_id}: Otrzymano rozkaz przerwania marszu! ({inter.cause})")
                return False
        return True

    def _mission_lifecycle(self):
        """
        Cykl życia pojedynczej misji ratunkowej w czasie SimPy.
        """
        # 1. MOBILIZACJA: jeśli to ochotnik wzywany z bazy/domu
        if self.is_volunteer and self.current_node == self.base_node:
            self.state = RescuerState.MOBILIZING
            print(f"[{self.env.now:.1f} min] {self.agent_id}: Wezwanie ochotnika. Mobilizacja (5 min)...")
            yield self.env.timeout(5.0)

        # 2. EN_ROUTE: Marsz do poszkodowanego
        self.state = RescuerState.EN_ROUTE
        print(
            f"[{self.env.now:.1f} min] {self.agent_id}: Wyrusza do wypadku {self.current_incident.incident_id} (węzeł {self.current_incident.target_node})...")

        reached_target = yield from self._travel_to(self.current_incident.target_node)
        if not reached_target:
            return  # Marsz został przerwany przez dyspozytora

        # 3. ON_SCENE: Działania medyczne na miejscu wypadku
        self.state = RescuerState.ON_SCENE
        print(
            f"[{self.env.now:.1f} min] {self.agent_id}: Dotarł na miejsce wypadku {self.current_incident.incident_id}. Udziela pomocy...")

        yield self.env.timeout(self.current_incident.rescue_duration)
        self.current_incident.is_resolved = True
        print(
            f"[{self.env.now:.1f} min] {self.agent_id}: Zakończył akcję ratunkową {self.current_incident.incident_id}!")

        # 4. RETURNING: Powrót do bazy
        if self.current_node != self.base_node:
            self.state = RescuerState.RETURNING
            print(f"[{self.env.now:.1f} min] {self.agent_id}: Wraca do bazy {self.base_node}...")
            reached_base = yield from self._travel_to(self.base_node)
            if not reached_base:
                return

        # 5. IDLE: Ratownik z powrotem w bazie
        self.state = RescuerState.IDLE
        self.current_incident = None
        print(f"[{self.env.now:.1f} min] {self.agent_id}: Jest w bazie. Status: IDLE (gotowy do kolejnych wezwań).")