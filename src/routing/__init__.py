"""
Moduł Routing:
- routing_interface.py: Kontrakt AbstractRoutingService (get_edge_travel_time, get_path, get_total_time, get_travel_time)
- terrain_routing.py: Rzeczywista implementacja fizyki pojedynczego kroku (get_edge_travel_time) na grafie DEM (Lorentz + WiSAR)
- mock_routing.py: Serwis testowy do symulacji agentowej
- weather_conditions.py: Modyfikatory meteorologiczne
"""

from src.routing.routing_interface import AbstractRoutingService
from src.routing.mock_routing import MockRoutingService
from src.routing.weather_conditions import WeatherConditions

try:
    from src.routing.terrain_routing import TerrainRoutingService
except ImportError:
    TerrainRoutingService = None

__all__ = [
    "AbstractRoutingService",
    "MockRoutingService",
    "TerrainRoutingService",
    "WeatherConditions",
]
