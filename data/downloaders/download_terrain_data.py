#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Skrypt pobierający dane geograficzne dla Parku Narodowego (granice i rzędne wysokościowe DEM).
Lokalizacja: data/downloaders/download_terrain_data.py
Uruchomienie:
    python data/downloaders/download_terrain_data.py --step 100
"""

import sys
import argparse
import datetime
from pathlib import Path

# Dołączenie głównego folderu projektu do sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.downloaders.terrain_downloader import TerrainDownloader


def main():
    parser = argparse.ArgumentParser(
        description="Pobieranie i lokalny zapis danych geograficznych Parku Narodowego (granice i rzędne DEM)."
    )
    parser.add_argument(
        "--area",
        type=str,
        default="Gorczański Park Narodowy, Poland",
        help="Nazwa obszaru do pobrania z OpenStreetMap"
    )
    parser.add_argument(
        "--step",
        type=float,
        default=100.0,
        help="Krok regularnej siatki pomiarowej w metrach (np. 100, 200, 350)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Ścieżka do pliku wyjściowego JSON z punktami (domyślnie: data/dem/terrain_points.json)"
    )
    parser.add_argument(
        "--boundary-output",
        type=str,
        default=None,
        help="Ścieżka do pliku GeoJSON z granicami (domyślnie: data/trails/park_boundary.geojson)"
    )
    parser.add_argument(
        "--dem-file",
        type=str,
        default=None,
        help="Opcjonalna ścieżka do lokalnego pliku rastrowego GeoTIFF NMT"
    )
    parser.add_argument(
        "--cache-file",
        type=str,
        default=None,
        help="Ścieżka do pliku cache wysokości (domyślnie: data/dem/elevation_cache.json)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=70,
        help="Liczba współrzędnych na zapytanie URL (zalecane: 60-80)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.45,
        help="Odstęp w sekundach między zapytaniami do API"
    )

    args = parser.parse_args()

    output_points_path = Path(args.output) if args.output else PROJECT_ROOT / "data" / "dem" / "terrain_points.json"
    output_boundary_path = Path(args.boundary_output) if args.boundary_output else PROJECT_ROOT / "data" / "trails" / "park_boundary.geojson"
    cache_path = Path(args.cache_file) if args.cache_file else PROJECT_ROOT / "data" / "dem" / "elevation_cache.json"

    print("=" * 80)
    print(" POBIERANIE I LOKALNY ZAPIS DANYCH GEOGRAFICZNYCH (DOWNLOADER)")
    print("=" * 80)
    print(f" Obszar badań:          {args.area}")
    print(f" Rozdzielczość (krok):  {args.step:.1f} m")
    print(f" Plik punktów (JSON):   {output_points_path}")
    print(f" Plik granic (GeoJSON): {output_boundary_path}")
    print(f" Plik cache wysokości:  {cache_path}")
    print(f" Tryb pobierania:       BRAK LIMITU CZASOWEGO (automatyczne ponawianie przy 429)")
    print("=" * 80)

    downloader = TerrainDownloader(metric_crs="EPSG:2180")

    # 1. Pobranie i zapis granic
    gdf_wgs84, polygon_metric = downloader.fetch_boundary(args.area)
    downloader.save_boundary_geojson(gdf_wgs84, str(output_boundary_path))

    # 2. Generowanie siatki w układzie metrycznym EPSG:2180
    grid_points = downloader.generate_grid_points(polygon_metric, step_meters=args.step)

    # 3. Pobranie wysokości
    grid_points = downloader.assign_elevations(
        grid_points=grid_points,
        dem_raster_path=args.dem_file,
        cache_path=str(cache_path),
        batch_size=args.batch_size,
        request_delay=args.delay,
        unlimited_wait=True
    )

    # 4. Zapis punktów terenu z metadanymi
    elevations = [p["z"] for p in grid_points]
    bounds_metric = list(polygon_metric.bounds)

    metadata = {
        "area_name": args.area,
        "step_meters": float(args.step),
        "metric_crs": "EPSG:2180",
        "created_at": datetime.datetime.now().isoformat(),
        "total_points": len(grid_points),
        "min_elevation_m": round(float(min(elevations)), 1),
        "max_elevation_m": round(float(max(elevations)), 1),
        "bounds_metric_epsg2180": bounds_metric
    }

    downloader.save_terrain_points(
        grid_points=grid_points,
        output_path=str(output_points_path),
        metadata=metadata
    )

    print("\n" + "=" * 80)
    print(" PODSUMOWANIE:")
    print(f" Pobrana liczba punktów:   {len(grid_points):,}")
    print(f" Zakres wysokości n.p.m.:  min = {min(elevations):.1f} m, max = {max(elevations):.1f} m")
    print(f" Zapisano punkty terenu:   {output_points_path}")
    print(f" Zapisano granice parku:   {output_boundary_path}")
    print(" Następny krok: uruchom budowę grafu terenu (mapper):")
    print(" -> python data/mappers/build_terrain_graph.py")
    print("=" * 80)


if __name__ == "__main__":
    main()
