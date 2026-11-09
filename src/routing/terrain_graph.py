import math
import json
import time
import urllib.request
import urllib.parse
from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path

import numpy as np
import networkx as nx
import osmnx as ox
import geopandas as gpd
import shapely.geometry as geom
from pyproj import Transformer


class TerrainGridGraphBuilder:
    """
    Generator i zarządca grafu przestrzennego siatki terenu (2D/3D).

    Odpowiada za:
    - Pobieranie i zapis obrysów granic terenu (np. Parku Narodowego)
    - Generowanie dyskretnej siatki punktów w układzie metrycznym (EPSG:2180)
    - Pobieranie wysokości n.p.m. (z pliku NMT/GeoTIFF lub Copernicus DEM online bez limitu czasu)
    - Budowę grafu skierowanego z 8-kierunkowym sąsiedztwem i nachyleniami stoku
    - Zapis i odczyt danych z lokalnych plików (GeoJSON, JSON, GraphML)
    """

    def __init__(self, metric_crs: str = "EPSG:2180"):
        """
        :param metric_crs: Układ metryczny (dla Polski domyślnie EPSG:2180 - PUWG 1992).
        """
        self.metric_crs = metric_crs
        self.transformer_to_metric = Transformer.from_crs("EPSG:4326", metric_crs, always_xy=True)
        self.transformer_to_wgs84 = Transformer.from_crs(metric_crs, "EPSG:4326", always_xy=True)

    def fetch_boundary(self, area_name: str) -> Tuple[gpd.GeoDataFrame, geom.base.BaseGeometry]:
        """
        Pobiera obrys granicy obszaru z OpenStreetMap i rzutuje do układu metrycznego.
        """
        print(f"[*] Pobieranie granic obszaru z OpenStreetMap: '{area_name}'...")
        gdf = ox.geocode_to_gdf(area_name)
        gdf_metric = gdf.to_crs(self.metric_crs)

        # Obsługa union w zależności od wersji Shapely/GeoPandas
        if hasattr(gdf_metric.geometry, "union_all"):
            polygon_metric = gdf_metric.geometry.union_all()
        else:
            polygon_metric = gdf_metric.geometry.unary_union

        return gdf, polygon_metric

    def save_boundary_geojson(self, gdf: gpd.GeoDataFrame, output_path: str):
        """
        Zapisuje geometrię granic do pliku GeoJSON.
        """
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_file(str(out_file), driver="GeoJSON")
        print(f"[*] Granice obszaru zapisane lokalnie w: {out_file}")

    def generate_grid_points(
        self,
        polygon_metric: geom.base.BaseGeometry,
        step_meters: float = 100.0
    ) -> List[Dict[str, Any]]:
        """
        Tworzy regularną siatkę punktów w układzie metrycznym i filtruje punkty wewnątrz poligonu.
        """
        print(f"[*] Generowanie siatki regularnej o kroku {step_meters:.0f} m...")
        minx, miny, maxx, maxy = polygon_metric.bounds

        xs = np.arange(minx, maxx + step_meters, step_meters)
        ys = np.arange(miny, maxy + step_meters, step_meters)

        grid_points = []
        for i, x in enumerate(xs):
            for j, y in enumerate(ys):
                pt = geom.Point(x, y)
                if polygon_metric.contains(pt):
                    lon, lat = self.transformer_to_wgs84.transform(x, y)
                    grid_points.append({
                        "grid_i": int(i),
                        "grid_j": int(j),
                        "x_metric": round(float(x), 2),
                        "y_metric": round(float(y), 2),
                        "x": round(float(lon), 6),  # Długość geograficzna WGS84
                        "y": round(float(lat), 6),  # Szerokość geograficzna WGS84
                        "z": 0.0                    # Do uzupełnienia
                    })

        print(f" -> Utworzono {len(grid_points):,} punktów pomiarowych wewnątrz granic.")
        return grid_points

    def assign_elevations(
        self,
        grid_points: List[Dict[str, Any]],
        dem_raster_path: Optional[str] = None,
        cache_path: Optional[str] = None,
        batch_size: int = 70,
        request_delay: float = 0.4,
        unlimited_wait: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Pobiera rzędne wysokościowe (z) dla punktów terenu.

        - Opcja A: Z lokalnego rastra GeoTIFF (DEM/NMT) przez rasterio.
        - Opcja B: Z API Copernicus DEM (Open-Meteo) z bezterminowym oczekiwaniem i odpornością
                   na HTTP 429 (Too Many Requests), natychmiastowym zapisem cache po każdej partii.
        """
        print(f"[*] Pozyskiwanie rzędnych wysokościowych dla {len(grid_points):,} punktów...")

        # 1. Sprawdzenie lokalnego pliku rastrowego GeoTIFF
        if dem_raster_path and Path(dem_raster_path).is_file():
            import rasterio
            print(f" -> Odczyt z lokalnego pliku NMT: {dem_raster_path}")
            with rasterio.open(dem_raster_path) as src:
                if src.crs and str(src.crs).upper() == self.metric_crs.upper():
                    coords = [(p["x_metric"], p["y_metric"]) for p in grid_points]
                else:
                    coords = [(p["x"], p["y"]) for p in grid_points]

                samples = list(src.sample(coords))
                for pt, sample in zip(grid_points, samples):
                    val = float(sample[0])
                    pt["z"] = round(val, 1) if val != src.nodata else 0.0
            print(" -> Pomyślnie wczytano wysokości z pliku rastrowego.")
            return grid_points

        # 2. Pobieranie z API Open-Meteo (Copernicus DEM 30m) z lokalnym cache
        if cache_path is None:
            cache_path = str(Path(__file__).resolve().parent.parent.parent / "data" / "dem" / "elevation_cache.json")

        cache_file = Path(cache_path)
        cache: Dict[str, float] = {}
        if cache_file.is_file():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                print(f" -> Załadowano {len(cache):,} punktów z lokalnego cache ({cache_file.name}).")
            except Exception as e:
                print(f" [!] Błąd odczytu pliku cache: {e}")

        # Przypisanie znanych wartości z cache
        missing_points: List[Dict[str, Any]] = []
        cached_count = 0
        for pt in grid_points:
            key = f"{pt['x']:.4f}_{pt['y']:.4f}"
            if key in cache:
                pt["z"] = cache[key]
                cached_count += 1
            else:
                missing_points.append(pt)

        if cached_count > 0:
            print(f" -> Dopasowano z cache: {cached_count:,} / {len(grid_points):,} punktów ({(cached_count/len(grid_points)*100):.1f}%).")

        if not missing_points:
            print(" -> Wszystkie wysokości są już w lokalnym pliku cache!")
            return grid_points

        print(f" -> Do pobrania pozostało {len(missing_points):,} punktów.")
        print(f" -> Rozpoczynanie pobierania online (Copernicus DEM 30m)...")
        if unlimited_wait:
            print(" -> Tryb bez limitu czasowego aktywny: w razie limitu serwera (HTTP 429) program będzie cierpliwie czekać i ponawiać.")

        total_missing = len(missing_points)
        start_time = time.time()

        for start_idx in range(0, total_missing, batch_size):
            end_idx = min(start_idx + batch_size, total_missing)
            batch = missing_points[start_idx:end_idx]

            lats = ",".join(f"{p['y']:.4f}" for p in batch)
            lons = ",".join(f"{p['x']:.4f}" for p in batch)
            url = f"https://api.open-meteo.com/v1/elevation?latitude={lats}&longitude={lons}"

            attempt = 0
            success = False

            while not success:
                attempt += 1
                try:
                    req = urllib.request.Request(
                        url,
                        headers={"User-Agent": "GOPR-Simulation-Terrain/1.0 (Educational Academic Project)"}
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = json.loads(resp.read().decode())
                        elevations = data.get("elevation", [])
                        for pt, elev in zip(batch, elevations):
                            if elev is not None:
                                val = round(float(elev), 1)
                            else:
                                val = 0.0
                            pt["z"] = val
                            key = f"{pt['x']:.4f}_{pt['y']:.4f}"
                            cache[key] = val

                        success = True

                        # Zapis cache na dysk na bieżąco po KAŻDEJ udanej partii
                        try:
                            cache_file.parent.mkdir(parents=True, exist_ok=True)
                            with open(cache_file, "w", encoding="utf-8") as f:
                                json.dump(cache, f, indent=2)
                        except Exception:
                            pass

                except urllib.error.HTTPError as err:
                    if err.code == 429:
                        wait_seconds = min(5 * attempt, 60)
                        print(
                            f"\n [HTTP 429 - Limit zapytań serwera] Oczekiwanie {wait_seconds}s przed ponowieniem (próba {attempt})...",
                            flush=True
                        )
                        time.sleep(wait_seconds)
                    else:
                        print(f"\n [Błąd HTTP {err.code}: {err.reason}] Oczekiwanie 5s (próba {attempt})...", flush=True)
                        time.sleep(5)
                except Exception as err:
                    print(f"\n [Błąd sieci: {err}] Oczekiwanie 5s (próba {attempt})...", flush=True)
                    time.sleep(5)

                if not unlimited_wait and attempt >= 10:
                    print(f"\n [!] Przekroczono limit prób w trybie ograniczonym dla partii {start_idx}-{end_idx}.")
                    break

            # Odstęp czasowy między zapytaniami, aby nie prowokować limitu 429
            time.sleep(request_delay)

            # Pasek postępu i szacowanie czasu
            done_so_far = cached_count + end_idx
            pct = done_so_far / len(grid_points) * 100.0
            elapsed = time.time() - start_time
            rate = end_idx / elapsed if elapsed > 0 else 1.0
            eta_seconds = (total_missing - end_idx) / rate if rate > 0 else 0
            eta_min = int(eta_seconds // 60)
            eta_sec = int(eta_seconds % 60)

            print(
                f"\r -> Postęp pobierania: {done_so_far:,} / {len(grid_points):,} ({pct:.1f}%) | "
                f"Pozostały szacowany czas: {eta_min:02d}m {eta_sec:02d}s",
                end="",
                flush=True
            )

        print(f"\n[*] Pobieranie wysokości zakończone sukcesem! Zapisano dane w cache: {cache_file.name}")
        return grid_points

    def save_terrain_points(
        self,
        grid_points: List[Dict[str, Any]],
        output_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Zapisuje pełną listę punktów pomiarowych terenu z metadanymi do pliku JSON.
        """
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "metadata": metadata or {},
            "total_points": len(grid_points),
            "points": grid_points
        }

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        print(f"[*] Dane terenu zapisane do pliku: {out_file} ({len(grid_points):,} punktów)")

    def load_terrain_points(self, input_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Wczytuje listę punktów terenu z pliku JSON (działanie w 100% offline).
        """
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
        Buduje skierowany graf przestrzenny terenu (8-kierunkowe sąsiedztwo w siatce)
        i wylicza dokładne odległości (2D, 3D) oraz nachylenie terenu dla każdej krawędzi.
        Działa całkowicie lokalnie (offline).
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

        # Słownik do szybkiego wyszukiwania sąsiadów w siatce po współrzędnych (i, j)
        grid_map: Dict[Tuple[int, int], str] = {}
        for pt in grid_points:
            node_id = f"N_{pt['grid_i']}_{pt['grid_j']}"
            grid_map[(pt["grid_i"], pt["grid_j"])] = node_id
            G.add_node(
                node_id,
                x=float(pt["x"]),                 # WGS84 długość (lon)
                y=float(pt["y"]),                 # WGS84 szerokość (lat)
                z=float(pt["z"]),                 # Wysokość n.p.m. w metrach
                x_metric=float(pt["x_metric"]),   # Metry EPSG:2180
                y_metric=float(pt["y_metric"]),   # Metry EPSG:2180
                grid_i=int(pt["grid_i"]),
                grid_j=int(pt["grid_j"])
            )

        # 8 kierunków przemieszczania się w siatce terenu
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

                    # 1. Odległość w poziomie w metrach (rzut 2D)
                    dx = v_node["x_metric"] - u_node["x_metric"]
                    dy = v_node["y_metric"] - u_node["y_metric"]
                    dist_2d = math.hypot(dx, dy)

                    # 2. Różnica wysokości (dz): dodatnia pod górę, ujemna w dół
                    dz = v_node["z"] - u_node["z"]

                    # 3. Rzeczywista odległość w przestrzeni 3D
                    dist_3d = math.sqrt(dist_2d**2 + dz**2)

                    # 4. Nachylenie terenu
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
        Zapewnia kompatybilność ze specyfikacją GraphML (konwertuje listy/słowniki na łańcuchy znaków).
        """
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        # GraphML akceptuje wyłącznie typy skalarne (int, float, str, bool)
        for k, v in list(G.graph.items()):
            if isinstance(v, (list, tuple, dict)):
                G.graph[k] = json.dumps(v)
            elif not isinstance(v, (int, float, str, bool)):
                G.graph[k] = str(v)

        nx.write_graphml(G, str(out_file))
        print(f"[*] Graf pomyślnie zapisany w pliku: {out_file}")

    def load_graph(self, input_path: str) -> nx.DiGraph:
        """
        Wczytuje graf z formatu GraphML i zapewnia właściwe typy liczbowe atrybutów.
        """
        in_file = Path(input_path)
        if not in_file.is_file():
            raise FileNotFoundError(f"Nie odnaleziono pliku grafu: {in_file}")

        G = nx.read_graphml(str(in_file))

        # GraphML wczytuje atrybuty często jako łańcuchy znaków — rzutujemy na float/int
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

        print(f"[*] Wczytano graf: {G.number_of_nodes():,} węzłów, {G.number_of_edges():,} krawędzi z: {in_file}")
        return G

    def build(
        self,
        area_name: str = "Gorczański Park Narodowy, Poland",
        step_meters: float = 250.0,
        dem_raster_path: Optional[str] = None,
        save_graphml_path: Optional[str] = None
    ) -> nx.DiGraph:
        """
        Metoda kompatybilności wstecznej: wykonuje pełny ciąg operacji.
        """
        _, polygon_metric = self.fetch_boundary(area_name)
        grid_points = self.generate_grid_points(polygon_metric, step_meters=step_meters)
        grid_points = self.assign_elevations(grid_points, dem_raster_path=dem_raster_path)
        metadata = {"area_name": area_name, "step_meters": step_meters, "crs": self.metric_crs}
        G = self.build_network_graph(grid_points, metadata=metadata)

        if save_graphml_path:
            self.save_graph(G, save_graphml_path)

        return G
