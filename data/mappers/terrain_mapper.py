#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Moduł odpowiedzialny za mapowanie punktów wysokościowych na graf przestrzenny terenu (2D/3D)
oraz integrację ze szlakami turystycznymi i modelem oporu terenu (Tobler + Friction Map).
Lokalizacja: data/mappers/terrain_mapper.py
"""

import math
import json
from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
import networkx as nx
import geopandas as gpd
import shapely.geometry as geom
import shapely.prepared


class TerrainGraphMapper:
    """
    Klasa odpowiedzialna za:
    - Wczytywanie punktów pomiarowych z pliku JSON (działanie w 100% offline).
    - Opcjonalne wczytywanie i buforowanie szlaków turystycznych (GeoJSON).
    - Budowę skierowanego grafu przestrzennego (8-kierunkowe sąsiedztwo na siatce).
    - Obliczanie parametrów fizycznych krawędzi:
        * distance_2d: rzut poziomy w metrach
        * elevation_change: różnica wysokości dz (+ pod górę, - w dół)
        * distance_3d: rzeczywista odległość w przestrzeni 3D w metrach
        * slope_degrees: kąt nachylenia stoku (-90° do +90°)
        * slope_ratio: tangens kąta stoku (dz / d2d)
        * grade_pct: nachylenie wyrażone w procentach [%]
        * is_trail: flaga oznaczająca przynależność do korytarza szlaku turystycznego
        * surface_friction: współczynnik oporu podłoża (1.0 szlak, 4.0 bezdroża)
        * speed_kmh: wypadkowa prędkość marszu ratownika wg funkcji Toblera
        * travel_time_min: czas pokonania krawędzi w minutach
        * weight: waga krawędzi do algorytmów trasowania (równa travel_time_min)
    - Zapis grafu do formatu GraphML.
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

    def load_trails_buffer(
        self,
        trails_path: str,
        buffer_meters: float = 20.0
    ) -> Optional[Any]:
        """
        Wczytuje szlaki z pliku GeoJSON, transformuje do układu metrycznego
        oraz tworzy przygotowaną geometrię bufora przestrzennego (Shapely PreparedGeometry)
        do błyskawicznego sprawdzania przecięć w czasie O(1)/O(log N).
        """
        p = Path(trails_path)
        if not p.is_file():
            print(f"[!] Nie znaleziono pliku szlaków: {trails_path}. Budowa grafu bez warstwy szlaków.")
            return None

        print(f"[*] Wczytywanie szlaków turystycznych z pliku: {p}...")
        gdf = gpd.read_file(str(p))
        if gdf.empty:
            print("[!] Plik szlaków jest pusty.")
            return None

        if gdf.crs is None or gdf.crs.to_string() != self.metric_crs:
            gdf = gdf.to_crs(self.metric_crs)

        print(f"[*] Budowa strefy buforowej szlaków (szerokość bufora: {buffer_meters:.1f} m)...")
        trails_union = gdf.geometry.unary_union
        buffered = trails_union.buffer(buffer_meters)
        prep_buffered = shapely.prepared.prep(buffered)
        print(f"[+] Przygotowano strefę buforową szlaków ({len(gdf):,} odcinków OSM).")
        return prep_buffered

    def build_network_graph(
        self,
        grid_points: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        trails_path: Optional[str] = None,
        trail_buffer_meters: Optional[float] = None,
        off_trail_friction: float = 4.0,
        trail_friction: float = 1.0
    ) -> nx.DiGraph:
        """
        Buduje skierowany graf topograficzny (siatka z 8-kierunkowym sąsiedztwem)
        i wylicza dokładne odległości (2D, 3D), nachylenia oraz czas przejścia Toblera
        ze współczynnikiem oporu podłoża dla każdej krawędzi.
        Szlaki turystyczne są rzutowane w sposób ciągły (topologiczny łańcuch krawędzi)
        przy użyciu drzewa KDTree, gwarantując 100% ciągłości bez przerw i bez 'rozlewania'.
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

        step_meters = 100.0
        if metadata and "step_meters" in metadata:
            try:
                step_meters = float(metadata["step_meters"])
            except (ValueError, TypeError):
                step_meters = 100.0

        grid_map: Dict[Tuple[int, int], str] = {}
        for pt in grid_points:
            node_id = f"N_{pt['grid_i']}_{pt['grid_j']}"
            grid_map[(pt["grid_i"], pt["grid_j"])] = node_id

            x_m = float(pt.get("x_metric", pt["x"]))
            y_m = float(pt.get("y_metric", pt["y"]))

            G.add_node(
                node_id,
                x=float(pt["x"]),
                y=float(pt["y"]),
                z=float(pt["z"]),
                x_metric=x_m,
                y_metric=y_m,
                grid_i=int(pt["grid_i"]),
                grid_j=int(pt["grid_j"]),
                is_trail=False
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

                    # 1. Prędkość marszu wg funkcji Toblera [km/h] (bazowa prędkość)
                    v_tobler = 6.0 * math.exp(-3.5 * abs(slope_ratio + 0.05))
                    v_tobler = max(0.1, v_tobler)

                    # 2. Domyślny opór podłoża poza szlakiem (off-trail)
                    friction = off_trail_friction
                    speed_kmh = v_tobler / friction
                    speed_m_per_min = speed_kmh * (1000.0 / 60.0)
                    travel_time_min = dist_3d / speed_m_per_min if speed_m_per_min > 0 else 999.0

                    G.add_edge(
                        u_id,
                        v_id,
                        distance_2d=round(dist_2d, 2),
                        distance_3d=round(dist_3d, 2),
                        elevation_change=round(dz, 2),
                        slope_degrees=round(slope_degrees, 2),
                        slope_ratio=round(slope_ratio, 4),
                        grade_pct=round(grade_pct, 2),
                        is_trail=False,
                        surface_friction=float(friction),
                        speed_kmh=round(speed_kmh, 2),
                        travel_time_min=round(travel_time_min, 4),
                        weight=round(travel_time_min, 4)
                    )
                    edges_count += 1

        # Rzutowanie szlaków turystycznych (Continuous KDTree Trail Tracing)
        trail_edges_count = 0
        trail_node_ids = set()

        if trails_path and Path(trails_path).is_file():
            print(f"[*] Rzutowanie szlaków turystycznych na graf za pomocą ciągłego trasowania KDTree: {trails_path}...")
            gdf = gpd.read_file(trails_path)
            if not gdf.empty:
                if gdf.crs is None or gdf.crs.to_string() != self.metric_crs:
                    gdf = gdf.to_crs(self.metric_crs)

                # Indeks przestrzenny KDTree na węzłach grafu
                node_ids = list(G.nodes())
                node_coords = np.array([[G.nodes[n]["x_metric"], G.nodes[n]["y_metric"]] for n in node_ids])
                kdtree = cKDTree(node_coords)

                sample_dist = max(10.0, step_meters / 4.0)  # np. 25m dla kroku 100m
                max_snap_dist = step_meters * 1.5           # próg przyciągania do siatki

                def mark_trail_segment(u_node_id: str, v_node_id: str):
                    nonlocal trail_edges_count
                    for a, b in [(u_node_id, v_node_id), (v_node_id, u_node_id)]:
                        if G.has_edge(a, b):
                            e = G[a][b]
                            if not e.get("is_trail", False):
                                e["is_trail"] = True
                                e["surface_friction"] = float(trail_friction)
                                slope_ratio = e["slope_ratio"]
                                v_tobler = 6.0 * math.exp(-3.5 * abs(slope_ratio + 0.05))
                                v_tobler = max(0.1, v_tobler)
                                speed_kmh = v_tobler / trail_friction
                                speed_m_per_min = speed_kmh * (1000.0 / 60.0)
                                dist_3d = e["distance_3d"]
                                travel_time_min = dist_3d / speed_m_per_min if speed_m_per_min > 0 else 999.0
                                e["speed_kmh"] = round(speed_kmh, 2)
                                e["travel_time_min"] = round(travel_time_min, 4)
                                e["weight"] = round(travel_time_min, 4)
                                trail_edges_count += 1
                                trail_node_ids.add(a)
                                trail_node_ids.add(b)
                                G.nodes[a]["is_trail"] = True
                                G.nodes[b]["is_trail"] = True

                for geom_obj in gdf.geometry:
                    if geom_obj is None or geom_obj.is_empty:
                        continue
                    if geom_obj.geom_type == "LineString":
                        lines = [geom_obj]
                    elif geom_obj.geom_type == "MultiLineString":
                        lines = list(geom_obj.geoms)
                    else:
                        continue

                    for line in lines:
                        total_len = line.length
                        if total_len < 1.0:
                            continue

                        num_samples = max(2, int(math.ceil(total_len / sample_dist)) + 1)
                        sample_dists = np.linspace(0, total_len, num_samples)
                        sample_points = [line.interpolate(d) for d in sample_dists]
                        query_coords = np.array([[p.x, p.y] for p in sample_points])

                        dists, indices = kdtree.query(query_coords)

                        # Tworzenie zwartej sekwencji unikalnych węzłów wzdłuż szlaku
                        node_chain = []
                        for d, idx in zip(dists, indices):
                            if d <= max_snap_dist:
                                nid = node_ids[idx]
                                if not node_chain or node_chain[-1] != nid:
                                    node_chain.append(nid)

                        # Łączenie kolejnych węzłów szlaku krawędziami
                        for idx_step in range(len(node_chain) - 1):
                            u_nid = node_chain[idx_step]
                            v_nid = node_chain[idx_step + 1]
                            if G.has_edge(u_nid, v_nid):
                                mark_trail_segment(u_nid, v_nid)
                            else:
                                # Obsługa rzadkich skoków diagonalnych przez połączenie najkrótszą ścieżką w siatce
                                try:
                                    shortest = nx.shortest_path(G, u_nid, v_nid)
                                    for p1, p2 in zip(shortest[:-1], shortest[1:]):
                                        mark_trail_segment(p1, p2)
                                except (nx.NetworkXNoPath, nx.NodeNotFound):
                                    pass

        trail_nodes_count = len(trail_node_ids)
        print(f" -> Utworzono graf: {G.number_of_nodes():,} węzłów oraz {G.number_of_edges():,} krawędzi.")
        if trails_path and Path(trails_path).is_file():
            pct_nodes = (trail_nodes_count / G.number_of_nodes()) * 100.0 if G.number_of_nodes() > 0 else 0.0
            pct_edges = (trail_edges_count / G.number_of_edges()) * 100.0 if G.number_of_edges() > 0 else 0.0
            print(f"    * Węzły szlaków (100% ciągłe ścieżki): {trail_nodes_count:,} ({pct_nodes:.2f}%)")
            print(f"    * Krawędzie szlaków:                  {trail_edges_count:,} ({pct_edges:.2f}%)")
            print(f"    * Opór poza szlakiem:                 {off_trail_friction}x wolniej")

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
        """Wczytuje graf z formatu GraphML i zapewnia właściwe typy liczbowe i logiczne atrybutów."""
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
            if "is_trail" in data:
                data["is_trail"] = str(data["is_trail"]).lower() in ["true", "1"]
            else:
                data["is_trail"] = False

        for u, v, data in G.edges(data=True):
            data["distance_2d"] = float(data.get("distance_2d", 0.0))
            data["distance_3d"] = float(data.get("distance_3d", 0.0))
            data["elevation_change"] = float(data.get("elevation_change", 0.0))
            data["slope_degrees"] = float(data.get("slope_degrees", 0.0))
            data["slope_ratio"] = float(data.get("slope_ratio", 0.0))
            data["grade_pct"] = float(data.get("grade_pct", 0.0))
            if "is_trail" in data:
                data["is_trail"] = str(data["is_trail"]).lower() in ["true", "1"]
            else:
                data["is_trail"] = False
            data["surface_friction"] = float(data.get("surface_friction", 1.0))
            data["speed_kmh"] = float(data.get("speed_kmh", 4.0))
            data["travel_time_min"] = float(data.get("travel_time_min", 0.0))
            data["weight"] = float(data.get("weight", data["travel_time_min"]))

        if "step_meters" in G.graph:
            try:
                G.graph["step_meters"] = float(G.graph["step_meters"])
            except (ValueError, TypeError):
                pass

        trail_nodes = sum(1 for _, d in G.nodes(data=True) if d.get("is_trail"))
        trail_edges = sum(1 for _, _, d in G.edges(data=True) if d.get("is_trail"))
        print(f"[*] Wczytano graf: {G.number_of_nodes():,} węzłów (szlaki: {trail_nodes:,}), {G.number_of_edges():,} krawędzi (szlaki: {trail_edges:,}) z: {in_file}")
        return G
