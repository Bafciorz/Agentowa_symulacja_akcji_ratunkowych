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
        description="Pobieranie i lokalny zapis danych geograficznych dla Rejonu Operacyjnego GOPR w Gorcach (DEM)."
    )
    parser.add_argument(
        "--preset",
        type=str,
        default="gopr-gorce",
        choices=["gopr-gorce"],
        help="Profil obszaru operacyjnego (domyślnie: 'gopr-gorce' dla całego rejonu działań GOPR w Gorcach)"
    )
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
        default=None,
        help="Opcjonalny własny prostokątny zakres: min_lon min_lat max_lon max_lat (np. 19.92 49.46 20.45 49.68)"
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
        help="Ścieżka do pliku GeoJSON z granicami (domyślnie: data/trails/gopr_boundary.geojson)"
    )
    parser.add_argument(
        "--dem-file",
        type=str,
        default=None,
        help="Opcjonalna ścieżka do lokalnego pliku rastrowego GeoTIFF NMT (domyślnie: data/dem/gorce_dem.tif)"
    )

    args = parser.parse_args()

    output_points_path = Path(args.output) if args.output else PROJECT_ROOT / "data" / "dem" / "terrain_points.json"
    output_boundary_path = Path(args.boundary_output) if args.boundary_output else PROJECT_ROOT / "data" / "trails" / "gopr_boundary.geojson"

    area_display = "Rejon Operacyjny Grupy Podhalańskiej GOPR - Gorce" if not args.bbox else f"Własny BBox {args.bbox}"

    print("=" * 80)
    print(" POBIERANIE I LOKALNY ZAPIS DANYCH GEOGRAFICZNYCH GOPR (DOWNLOADER)")
    print("=" * 80)
    print(f" Obszar badań:          {area_display}")
    print(f" Rozdzielczość (krok):  {args.step:.1f} m")
    print(f" Plik punktów (JSON):   {output_points_path}")
    print(f" Plik granic (GeoJSON): {output_boundary_path}")
    print(f" Model wysokości:       Copernicus DEM 30m (GeoTIFF / rasterio)")
    print("=" * 80)

    downloader = TerrainDownloader(metric_crs="EPSG:2180")

    # 1. Pobranie lub utworzenie granic obszaru operacyjnego GOPR
    if args.bbox:
        min_lon, min_lat, max_lon, max_lat = args.bbox
        gdf_wgs84, polygon_metric = downloader.create_bbox_boundary(
            min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat, area_name="Własny BBox"
        )
        area_title = f"BBox [{min_lon:.2f}, {min_lat:.2f}, {max_lon:.2f}, {max_lat:.2f}]"
    else:
        gdf_wgs84, polygon_metric = downloader.get_preset_boundary(args.preset)
        area_title = "Rejon Operacyjny Grupy Podhalańskiej GOPR - Gorce"

    downloader.save_boundary_geojson(gdf_wgs84, str(output_boundary_path))

    # 2. Generowanie siatki w układzie metrycznym EPSG:2180
    grid_points = downloader.generate_grid_points(polygon_metric, step_meters=args.step)

    # 3. Pobranie wysokości (z lokalnego pliku GeoTIFF lub automatycznie pobranego rastra)
    grid_points = downloader.assign_elevations(
        grid_points=grid_points,
        dem_raster_path=args.dem_file
    )

    # 4. Zapis punktów terenu z metadanymi
    elevations = [p["z"] for p in grid_points]
    bounds_metric = list(polygon_metric.bounds)

    metadata = {
        "area_name": area_title,
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
    print(f" Zapisano granice obszaru: {output_boundary_path}")
    print(" Następny krok: uruchom budowę grafu terenu (mapper):")
    print(" -> python data/mappers/build_terrain_graph.py")
    print("=" * 80)


if __name__ == "__main__":
    main()
