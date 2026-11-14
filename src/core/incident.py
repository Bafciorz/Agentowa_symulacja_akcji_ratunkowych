import enum
from typing import Union, List, Dict
import simpy
from dataclasses import dataclass, field


class Priority (enum.IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Incident:
    incident_id : str
    target_node : Union[int, str]
    priority: Priority
    required_rescuers: int = 1
    rescue_duration: float  = 30.0 # czas akcji ratowniczej na miejscu
    created_at: float = 0.0# moment zglsozenia (czas SimPy)
    is_resolved: bool = False
    assigned_rescuers: List[str] = field(default_factory = list)

    arrival_events: List[simpy.Event] = field(default_factory=list)
    _rescuer_arrival_map: Dict[str, simpy.Event] = field(default_factory=dict)

    def init_events(self, env: simpy.Environment) -> None:
        """Inicjalizuje zdarzenia dotarcia dla wymaganej liczby ratowników."""
        if not self.arrival_events:
            self.arrival_events = [env.event() for _ in range(self.required_rescuers)]
            self._rescuer_arrival_map = {}

    def register_arrival(self, env: simpy.Environment, rescuer_id: str) -> simpy.Event:
        """
        Rejestruje dotarcie danego ratownika i odpala jego zdarzenie przybycia
        :param env:
        :param rescuer_id:
        :return:
        """

        self.init_events(env)

        if rescuer_id not in self._rescuer_arrival_map:
            assigned_idx = len(self._rescuer_arrival_map)
            if assigned_idx < len(self.arrival_events):
                event = self.arrival_events[assigned_idx]
            else:
                event = env.event()
                self.arrival_events.append(event)

            self._rescuer_arrival_map[rescuer_id] = event
            if not event.triggered:
                event.succeed()
            return event
        return self._rescuer_arrival_map[rescuer_id]

    def get_team_assembly_condition(self, env: simpy.Environment) -> simpy.AllOf:
        """
        Zwraca warunek simpy.AllOf, który odblokuje się w SimPy dokładnie w chwili,
        gdy WSZYSCY wymagani ratownicy (required_rescuers) zameldują się na miejscu.
        """
        self.init_events(env)
        return simpy.AllOf(env, self.arrival_events)