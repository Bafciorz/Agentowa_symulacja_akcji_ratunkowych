#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Moduł odpowiedzialny za pobieranie i zapis surowych danych przestrzennych (NMT/DEM oraz granice OSM).
Lokalizacja: data/downloaders/terrain_downloader.py
"""

import math
import json
import time
import urllib.request
import urllib.parse
from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path

import numpy as np
import osmnx as ox
import geopandas as gpd
import shapely.geometry as geom
from pyproj import Transformer


class TerrainDownloader:
    """
    Klasa odpowiedzialna za:
    - Pobieranie obrysów granic obszaru (np. Parku Narodowego) z OpenStreetMap.
    - Tworzenie regularnej dyskretnej siatki punktów w układzie metrycznym PUWG 1992 (EPSG:2180).
    - Pozyskiwanie wysokości n.p.m. dla punktów (Copernicus DEM 30m z Open-Meteo lub lokalnego pliku GeoTIFF).
    - Cierpliwe ponawianie prób przy ograniczeniach serwera (HTTP 429) - brak limitu czasowego.
    - Zapisywanie postępów w cache po każdej partii.
    - Zapisywanie punktów do pliku JSON oraz granic do GeoJSON.
    """

    def __init__(self, metric_crs: str = "EPSG:2180"):
        self.metric_crs = metric_crs
        self.transformer_to_metric = Transformer.from_crs("EPSG:4326", metric_crs, always_xy=True)
        self.transformer_to_wgs84 = Transformer.from_crs(metric_crs, "EPSG:4326", always_xy=True)

    def fetch_boundary(self, area_name: str) -> Tuple[gpd.GeoDataFrame, geom.base.BaseGeometry]:
        """Pobiera obrys granicy obszaru z OpenStreetMap i rzutuje do układu metrycznego."""
        print(f"[*] Pobieranie granic obszaru z OpenStreetMap: '{area_name}'...")
        gdf = ox.geocode_to_gdf(area_name)
        gdf_metric = gdf.to_crs(self.metric_crs)

        if hasattr(gdf_metric.geometry, "union_all"):
            polygon_metric = gdf_metric.geometry.union_all()
        else:
            polygon_metric = gdf_metric.geometry.unary_union

        return gdf, polygon_metric

    def save_boundary_geojson(self, gdf: gpd.GeoDataFrame, output_path: str):
        """Zapisuje geometrię granic do pliku GeoJSON."""
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_file(str(out_file), driver="GeoJSON")
        print(f"[*] Granice obszaru zapisane lokalnie w: {out_file}")

    def generate_grid_points(
        self,
        polygon_metric: geom.base.BaseGeometry,
        step_meters: float = 100.0
    ) -> List[Dict[str, Any]]:
        """Tworzy regularną siatkę punktów w układzie metrycznym wewnątrz poligonu terenu."""
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
                        "x": round(float(lon), 6),
                        "y": round(float(lat), 6),
                        "z": 0.0
                    })

        print(f" -> Utworzono {len(grid_points):,} punktów pomiarowych wewnątrz granic.")
        return grid_points

    def assign_elevations(
        self,
        grid_points: List[Dict[str, Any]],
        dem_raster_path: Optional[str] = None,
        cache_path: Optional[str] = None,
        batch_size: int = 70,
        request_delay: float = 0.45,
        unlimited_wait: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Pobiera rzędne wysokościowe (z) dla punktów terenu:
        1. Z lokalnego pliku rastrowego GeoTIFF (DEM/NMT).
        2. Lub online z API Copernicus DEM (Open-Meteo) bez limitu czasowego i z odpornością na HTTP 429.
        """
        print(f"[*] Pozyskiwanie rzędnych wysokościowych dla {len(grid_points):,} punktów...")

        # Wariant A: Lokalny raster GeoTIFF
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

        # Wariant B: Pobieranie online z cache i ponawianiem
        if cache_path is None:
            cache_path = str(Path(__file__).resolve().parent.parent / "dem" / "elevation_cache.json")

        cache_file = Path(cache_path)
        cache: Dict[str, float] = {}
        if cache_file.is_file():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                print(f" -> Załadowano {len(cache):,} punktów z lokalnego cache ({cache_file.name}).")
            except Exception as e:
                print(f" [!] Błąd odczytu pliku cache: {e}")

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
        print(" -> Rozpoczynanie pobierania online (Copernicus DEM 30m)...")
        if unlimited_wait:
            print(" -> Tryb bez limitu czasowego: w razie limitu serwera (HTTP 429) program będzie cierpliwie czekać i ponawiać.")

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
                            val = round(float(elev), 1) if elev is not None else 0.0
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
                    print(f"\n [Błąd połączenia/sieci: {err}] Oczekiwanie 5s (próba {attempt})...", flush=True)
                    time.sleep(5)

                if not unlimited_wait and attempt >= 10:
                    print(f"\n [!] Przekroczono limit prób w partii {start_idx}-{end_idx}.")
                    break

            time.sleep(request_delay)

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

        print(f"\n[*] Pobieranie wysokości zakończone! Zaktualizowano cache w: {cache_file.name}")
        return grid_points

    def save_terrain_points(
        self,
        grid_points: List[Dict[str, Any]],
        output_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Zapisuje listę punktów terenu z metadanymi do pliku JSON."""
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
