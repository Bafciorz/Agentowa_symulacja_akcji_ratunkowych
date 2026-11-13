import enum
from typing import Union, List

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
