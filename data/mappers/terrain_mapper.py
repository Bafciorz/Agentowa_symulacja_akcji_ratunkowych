#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Moduł odpowiedzialny za mapowanie punktów wysokościowych na graf przestrzenny terenu (2D/3D).
Lokalizacja: data/mappers/terrain_mapper.py
"""

import math
import json
from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path

import networkx as nx


class TerrainGraphMapper:
    """
    Klasa odpowiedzialna za:
    - Wczytywanie punktów pomiarowych z pliku JSON (działanie w 100% offline).
    - Budowę skierowanego grafu przestrzennego (8-kierunkowe sąsiedztwo na siatce).
    - Obliczanie parametrów fizycznych krawędzi:
        * distance_2d: rzut poziomy w metrach
        * elevation_change: różnica wysokości dz (+ pod górę, - w dół)
        * distance_3d: rzeczywista odległość w przestrzeni 3D w metrach
        * slope_degrees: kąt nachylenia stoku (-90° do +90°)
        * slope_ratio: tangens kąta stoku (dz / d2d)
        * grade_pct: nachylenie wyrażone w procentach [%]
    - Bezpieczny zapis grafu do formatu GraphML (z walidacją i serializacją typów).
    - Odczyt gotowego grafu z formatu GraphML.
    """

    def __init__(self, metric_crs: str = "EPSG:2180"):
        self.metric_crs = metric_crs

    def load_terrain_points(self, input_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Wczytuje listę punktów terenu z pliku JSON (100% offline)."""
        in_file = Path(input_path)
        if not in_file.is_file():
            raise FileNotFoundError(f"Nie odnaleziono pliku danych terenu: {in_file}")

        with open(in_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        points = data.get("points", [])
        metadata = data.get("metadata", {})
        print(f"[*] Wczytano {len(points):,} punktów terenu z pliku: {in_file}")
        return points, metadata

    def build_network_graph(
        self,
        grid_points: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> nx.DiGraph:
        """
        Buduje skierowany graf topograficzny (siatka z 8-kierunkowym sąsiedztwem)
        i wylicza dokładne odległości (2D, 3D) oraz nachylenia dla każdej krawędzi.
        """
        print(f"[*] Budowa grafu topograficznego dla {len(grid_points):,} punktów węzłowych...")
        G = nx.DiGraph()

        if metadata:
            for k, v in metadata.items():
                if isinstance(v, (int, float, str, bool)):
                    G.graph[k] = v
                elif isinstance(v, (list, tuple, dict)):
                    G.graph[k] = json.dumps(v)
                else:
                    G.graph[k] = str(v)

        grid_map: Dict[Tuple[int, int], str] = {}
        for pt in grid_points:
            node_id = f"N_{pt['grid_i']}_{pt['grid_j']}"
            grid_map[(pt["grid_i"], pt["grid_j"])] = node_id
            G.add_node(
                node_id,
                x=float(pt["x"]),
                y=float(pt["y"]),
                z=float(pt["z"]),
                x_metric=float(pt.get("x_metric", pt["x"])),
                y_metric=float(pt.get("y_metric", pt["y"])),
                grid_i=int(pt["grid_i"]),
                grid_j=int(pt["grid_j"])
            )

        # 8 kierunków sąsiedztwa w regularnej siatce
        neighbors_offsets = [
            (1, 0), (-1, 0), (0, 1), (0, -1),      # Ruch prostopadły: N, S, E, W
            (1, 1), (1, -1), (-1, 1), (-1, -1)     # Ruch po przekątnych: NE, NW, SE, SW
        ]

        edges_count = 0
        for (i, j), u_id in grid_map.items():
            u_node = G.nodes[u_id]
            for di, dj in neighbors_offsets:
                v_coords = (i + di, j + dj)
                if v_coords in grid_map:
                    v_id = grid_map[v_coords]
                    v_node = G.nodes[v_id]

                    dx = v_node["x_metric"] - u_node["x_metric"]
                    dy = v_node["y_metric"] - u_node["y_metric"]
                    dist_2d = math.hypot(dx, dy)

                    dz = v_node["z"] - u_node["z"]
                    dist_3d = math.sqrt(dist_2d**2 + dz**2)

                    slope_ratio = dz / dist_2d if dist_2d > 0 else 0.0
                    slope_degrees = math.degrees(math.atan2(dz, dist_2d))
                    grade_pct = slope_ratio * 100.0

                    G.add_edge(
                        u_id,
                        v_id,
                        distance_2d=round(dist_2d, 2),
                        distance_3d=round(dist_3d, 2),
                        elevation_change=round(dz, 2),
                        slope_degrees=round(slope_degrees, 2),
                        slope_ratio=round(slope_ratio, 4),
                        grade_pct=round(grade_pct, 2)
                    )
                    edges_count += 1

        print(f" -> Utworzono graf: {G.number_of_nodes():,} węzłów oraz {G.number_of_edges():,} krawędzi.")
        return G

    def save_graph(self, G: nx.DiGraph, output_path: str):
        """
        Zapisuje graf do uniwersalnego formatu GraphML.
        Zapewnia zgodność ze specyfikacją GraphML (zamiana typów złożonych na ciągi tekstowe).
        """
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        for k, v in list(G.graph.items()):
            if isinstance(v, (list, tuple, dict)):
                G.graph[k] = json.dumps(v)
            elif not isinstance(v, (int, float, str, bool)):
                G.graph[k] = str(v)

        nx.write_graphml(G, str(out_file))
        print(f"[*] Graf pomyślnie zapisany w pliku: {out_file}")

    def load_graph(self, input_path: str) -> nx.DiGraph:
        """Wczytuje graf z formatu GraphML i zapewnia właściwe typy liczbowe atrybutów."""
        in_file = Path(input_path)
        if not in_file.is_file():
            raise FileNotFoundError(f"Nie odnaleziono pliku grafu: {in_file}")

        G = nx.read_graphml(str(in_file))

        for node_id, data in G.nodes(data=True):
            data["x"] = float(data["x"])
            data["y"] = float(data["y"])
            data["z"] = float(data["z"])
            if "x_metric" in data:
                data["x_metric"] = float(data["x_metric"])
            if "y_metric" in data:
                data["y_metric"] = float(data["y_metric"])
            if "grid_i" in data:
                data["grid_i"] = int(data["grid_i"])
            if "grid_j" in data:
                data["grid_j"] = int(data["grid_j"])

        for u, v, data in G.edges(data=True):
            data["distance_2d"] = float(data.get("distance_2d", 0.0))
            data["distance_3d"] = float(data.get("distance_3d", 0.0))
            data["elevation_change"] = float(data.get("elevation_change", 0.0))
            data["slope_degrees"] = float(data.get("slope_degrees", 0.0))
            data["slope_ratio"] = float(data.get("slope_ratio", 0.0))
            data["grade_pct"] = float(data.get("grade_pct", 0.0))

        if "step_meters" in G.graph:
            try:
                G.graph["step_meters"] = float(G.graph["step_meters"])
            except (ValueError, TypeError):
                pass

        print(f"[*] Wczytano graf: {G.number_of_nodes():,} węzłów, {G.number_of_edges():,} krawędzi z: {in_file}")
        return G
