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

        self.dispatcher: Any = None

    def assign_incident (self, incident: Incident) -> simpy.Process:
        """
        przypisanie incydentu
        :param incident:
        :return: simpy.Process
        """
        self.current_incident = incident
        if self.agent_id not in incident.assigned_rescuers:
            incident.assigned_rescuers.append(self.agent_id)

        if self.process is None or not self.process.is_alive:
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
        while True:
            # Pętla obsługi incydentu (lub kolejnych incydentów z rzędu)
            while self.current_incident is not None:
                incident = self.current_incident
                # 2. EN_ROUTE: Marsz do poszkodowanego
                self.state = RescuerState.EN_ROUTE
                print(
                    f"[{self.env.now:.1f} min] {self.agent_id}: Wyrusza do wypadku {incident.incident_id} (węzeł {incident.target_node})...")
                reached_target = yield from self._travel_to(incident.target_node)
                if not reached_target:
                    # Marsz przerwany przez dyspozytora (np. Triage) -> sprawdzamy nowy cel
                    continue
                # 3. ON_SCENE: Rejestracja dotarcia i zbiórka zespołu (simpy.AllOf)
                self.state = RescuerState.ON_SCENE
                incident.register_arrival(self.env, self.agent_id)
                arrived = len(incident._rescuer_arrival_map)
                print(
                    f"[{self.env.now:.1f} min] {self.agent_id}: Dotarł na miejsce wypadku {incident.incident_id} [{arrived}/{incident.required_rescuers} ratowników].")
                # Czekamy na resztę zespołu (dla 1 ratownika przechodzi od razu):
                yield incident.get_team_assembly_condition(self.env)
                # Działania medyczne / pakowanie do noszy:
                print(
                    f"[{self.env.now:.1f} min] {self.agent_id}: Rozpoczyna działania ratownicze ({incident.rescue_duration} min)...")
                yield self.env.timeout(incident.rescue_duration)
                incident.is_resolved = True
                print(f"[{self.env.now:.1f} min] {self.agent_id}: Zakończył akcję ratunkową {incident.incident_id}!")
                self.current_incident = None
                # Sprawdzamy, czy dyspozytor ma kolejne zgłoszenie w kolejce:
                if self.dispatcher and self.dispatcher.notify_rescuer_available(self):
                    continue  # Idzie od razu do nowego wypadku!
            # 4. RETURNING: Brak zadań w kolejce -> powrót do bazy
            if self.current_node != self.base_node:
                self.state = RescuerState.RETURNING
                print(f"[{self.env.now:.1f} min] {self.agent_id}: Wraca do bazy {self.base_node}...")
                reached_base = yield from self._travel_to(self.base_node)
                if not reached_base:
                    # Jeśli w drodze powrotnej dostał wezwanie -> wraca do pętli wypadku
                    if self.current_incident is not None:
                        continue
            # 5. IDLE: Ratownik z powrotem w bazie
            self.state = RescuerState.IDLE
            print(f"[{self.env.now:.1f} min] {self.agent_id}: Jest w bazie. Status: IDLE (gotowy do kolejnych wezwań).")
            # Jeśli coś wpadło do kolejki w ostatniej chwili:
            if self.dispatcher and self.dispatcher.notify_rescuer_available(self):
                continue
            # Jeśli baza osiągnięta i brak zadań -> proces kończy bieg
            break