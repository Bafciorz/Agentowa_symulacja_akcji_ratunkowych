#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PROGRAM 1: Pobieranie i lokalny zapis danych geograficznych (Granice i Wysokości DEM).

Funkcjonalność:
- Pobiera wektorowe granice Parku Narodowego / obszaru z OpenStreetMap.
- Zapisuje granice do pliku GeoJSON w data/trails/park_boundary.geojson.
- Generuje dyskretną siatkę pomiarową w układzie metrycznym PUWG 1992 (EPSG:2180) o zadanym kroku (np. 100m, 200m).
- Pozyskuje rzędne wysokościowe n.p.m. dla każdego punktu siatki (z lokalnego pliku NMT lub online z modelu Copernicus DEM 30m).
- BRAK LIMITU CZASOWEGO: W razie nałożenia ograniczeń przez API (HTTP 429), program automatycznie czeka i ponawia próby aż do skutku.
- Postęp jest zapisywany w pliku cache na bieżąco po każdej partii (możliwość bezpiecznego przerwania i wznowienia bez utraty danych).
- Końcowy rezultat jest zapisywany do pliku data/dem/terrain_points.json.
"""

import sys
import argparse
import datetime
from pathlib import Path

# Dodanie katalogu projektu do sys.path
sys.path.append(str(Path(__file__).resolve().parent))

from src.routing.terrain_graph import TerrainGridGraphBuilder


def main():
    parser = argparse.ArgumentParser(
        description="Program 1: Pobieranie i lokalny zapis danych geograficznych Parku Narodowego (granice i rzędne DEM)."
    )
    parser.add_argument(
        "--area",
        type=str,
        default="Gorczański Park Narodowy, Poland",
        help="Nazwa obszaru do pobrania z OpenStreetMap (np. 'Gorczański Park Narodowy, Poland')"
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
        default="data/dem/terrain_points.json",
        help="Ścieżka do pliku wyjściowego JSON z punktami terenu i wysokościami"
    )
    parser.add_argument(
        "--boundary-output",
        type=str,
        default="data/trails/park_boundary.geojson",
        help="Ścieżka do pliku wyjściowego GeoJSON z granicami obszaru"
    )
    parser.add_argument(
        "--dem-file",
        type=str,
        default=None,
        help="Opcjonalna ścieżka do lokalnego pliku rastrowego GeoTIFF z Numerycznym Modelem Terenu (NMT)"
    )
    parser.add_argument(
        "--cache-file",
        type=str,
        default="data/dem/elevation_cache.json",
        help="Ścieżka do lokalnego pliku podręcznego (cache) wysokości"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=70,
        help="Liczba współrzędnych wysyłanych w jednym zapytaniu URL (zalecane: 60-80)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.45,
        help="Odstęp w sekundach między zapytaniami do API (zapobiega blokadom HTTP 429)"
    )

    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    output_points_path = project_root / args.output
    output_boundary_path = project_root / args.boundary_output
    cache_path = project_root / args.cache_file

    print("=" * 80)
    print(" PROGRAM 1: POBIERANIE I LOKALNY ZAPIS DANYCH GEOGRAFICZNYCH")
    print("=" * 80)
    print(f" Obszar badań:          {args.area}")
    print(f" Rozdzielczość (krok):  {args.step:.1f} m")
    print(f" Plik punktów (JSON):   {output_points_path}")
    print(f" Plik granic (GeoJSON): {output_boundary_path}")
    print(f" Plik cache wysokości:  {cache_path}")
    print(f" Tryb pobierania:       BRAK LIMITU CZASOWEGO (cierpliwe ponawianie prób)")
    print("=" * 80)

    builder = TerrainGridGraphBuilder(metric_crs="EPSG:2180")

    # Krok 1: Granice obszaru
    gdf_wgs84, polygon_metric = builder.fetch_boundary(args.area)
    builder.save_boundary_geojson(gdf_wgs84, str(output_boundary_path))

    # Krok 2: Generowanie siatki w układzie metrycznym EPSG:2180
    grid_points = builder.generate_grid_points(polygon_metric, step_meters=args.step)

    # Krok 3: Pobieranie rzędnych wysokościowych z API lub rastra
    grid_points = builder.assign_elevations(
        grid_points=grid_points,
        dem_raster_path=args.dem_file,
        cache_path=str(cache_path),
        batch_size=args.batch_size,
        request_delay=args.delay,
        unlimited_wait=True
    )

    # Krok 4: Zapis punktów terenu z metadanymi do pliku JSON
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

    builder.save_terrain_points(
        grid_points=grid_points,
        output_path=str(output_points_path),
        metadata=metadata
    )

    print("\n" + "=" * 80)
    print(" PODSUMOWANIE POBIERANIA DANYCH:")
    print("=" * 80)
    print(f" Liczba pobranych punktów: {len(grid_points):,}")
    print(f" Wysokość minimalna:       {min(elevations):.1f} m n.p.m.")
    print(f" Wysokość maksymalna:       {max(elevations):.1f} m n.p.m.")
    print(f" Plik punktów i wysokości: {output_points_path}")
    print(f" Plik granic parku:        {output_boundary_path}")
    print(" Możesz teraz uruchomić Program 2 (tworzenie grafu terenu):")
    print(f" -> python 2_build_terrain_graph.py")
    print("=" * 80)


if __name__ == "__main__":
    main()
