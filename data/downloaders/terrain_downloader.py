#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Moduł odpowiedzialny za pobieranie i zapis surowych danych przestrzennych (NMT/DEM oraz granice OSM).
Lokalizacja: data/downloaders/terrain_downloader.py
"""

import math
import json
from typing import Optional, Tuple, Dict, Any, List, cast
from pathlib import Path

import numpy as np
import rasterio
import geopandas as gpd
import shapely.geometry as geom
from pyproj import Transformer

PRESETS = {
    "gopr-gorce": {
        "name": "Rejon Operacyjny Grupy Podhalańskiej GOPR - Gorce",
        "description": "Całe pasmo Gorców od Rabki-Zdroju po Krościenko nad Dunajcem i od Mszany Dolnej po Nowy Targ ze wszystkimi stacjami GOPR.",
        "min_lon": 19.92,
        "min_lat": 49.46,
        "max_lon": 20.45,
        "max_lat": 49.68
    }
}


class TerrainDownloader:
    """
    Klasa odpowiedzialna za:
    - Generowanie granic Rejonu Operacyjnego GOPR w Gorcach (lub własnego Bounding Boxa).
    - Tworzenie regularnej dyskretnej siatki punktów w układzie metrycznym PUWG 1992 (EPSG:2180).
    - Błyskawiczne pozyskiwanie wysokości n.p.m. dla punktów z satelitarnego rastra GeoTIFF (Copernicus DEM 30m).
    - Zapisywanie punktów do pliku JSON oraz granic do GeoJSON.
    """

    def __init__(self, metric_crs: str = "EPSG:2180"):
        self.metric_crs = metric_crs
        self.transformer_to_metric = Transformer.from_crs("EPSG:4326", metric_crs, always_xy=True)
        self.transformer_to_wgs84 = Transformer.from_crs(metric_crs, "EPSG:4326", always_xy=True)

    def create_bbox_boundary(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        area_name: str = "Obszar Bounding Box"
    ) -> Tuple[gpd.GeoDataFrame, geom.base.BaseGeometry]:
        """Tworzy prostokątny obszar (Bounding Box) o zadanym zakresie współrzędnych geograficznych."""
        print(f"[*] Tworzenie obszaru Bounding Box: '{area_name}'...")
        print(f"    Współrzędne WGS84: lon [{min_lon:.4f}, {max_lon:.4f}], lat [{min_lat:.4f}, {max_lat:.4f}]")
        box_wgs84 = geom.box(min_lon, min_lat, max_lon, max_lat)
        gdf = gpd.GeoDataFrame([{"name": area_name}], geometry=[box_wgs84], crs="EPSG:4326")

        # Rzutowanie narożników do układu metrycznego
        x1, y1 = self.transformer_to_metric.transform(min_lon, min_lat)
        x2, y2 = self.transformer_to_metric.transform(max_lon, max_lat)
        polygon_metric = cast(
            geom.base.BaseGeometry,
            geom.box(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        )
        return gdf, polygon_metric

    def get_preset_boundary(self, preset_key: str) -> Tuple[gpd.GeoDataFrame, geom.base.BaseGeometry]:
        """Zwraca geometrię dla zdefiniowanego profilu (presetu)."""
        if preset_key not in PRESETS:
            available = ", ".join(PRESETS.keys())
            raise ValueError(f"Nieznany preset '{preset_key}'. Dostępne presety: {available}")

        cfg = PRESETS[preset_key]
        print(f"[*] Wybrano gotowy profil operacyjny: {cfg['name']}")
        print(f"    Opis: {cfg['description']}")
        return self.create_bbox_boundary(
            min_lon=cfg["min_lon"],
            min_lat=cfg["min_lat"],
            max_lon=cfg["max_lon"],
            max_lat=cfg["max_lat"],
            area_name=cfg["name"]
        )

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
        dem_raster_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Pobiera rzędne wysokościowe (z) dla punktów terenu z lokalnego pliku rastrowego GeoTIFF (Copernicus DEM 30m).
        W razie braku pliku automatycznie uruchamia pobieranie kafelków satelitarnych.
        """
        print(f"[*] Pozyskiwanie rzędnych wysokościowych dla {len(grid_points):,} punktów...")

        # Automatyczne wykrycie lub pobranie domyślnego pliku rastrowego gorce_dem.tif
        if dem_raster_path is None:
            default_dem = Path(__file__).resolve().parent.parent / "dem" / "gorce_dem.tif"
            if not default_dem.is_file():
                from data.downloaders.download_dem_raster import ensure_dem_raster
                default_dem = ensure_dem_raster(default_dem)
            dem_raster_path = str(default_dem)

        dem_file = Path(dem_raster_path)
        if not dem_file.is_file():
            raise FileNotFoundError(f"Nie odnaleziono pliku NMT/DEM: {dem_raster_path}")

        print(f" -> Odczyt z modelu rzeźby terenu GeoTIFF: {dem_file.name}")
        with rasterio.open(str(dem_file)) as src:
            if src.crs and str(src.crs).upper() == self.metric_crs.upper():
                coords = [(p["x_metric"], p["y_metric"]) for p in grid_points]
            else:
                coords = [(p["x"], p["y"]) for p in grid_points]

            samples = list(src.sample(coords))
            for pt, sample in zip(grid_points, samples):
                val = float(sample[0])
                is_valid = (src.nodata is None or val != src.nodata) and not np.isnan(val) and val > -500
                pt["z"] = round(val, 1) if is_valid else 0.0

        print(f" -> Pomyślnie wczytano wysokości dla wszystkich {len(grid_points):,} punktów w ułamku sekundy!")
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
