#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Skrypt pobierający szlaki turystyczne i ścieżki górskie z OpenStreetMap (OSM) dla Rejonu Operacyjnego GOPR.
Pobiera oficjalne szlaki PTTK (relacje route=hiking/foot) oraz ścieżki górskie (highway=path),
eliminując niepotrzebne drogi gospodarcze/zrywkowe.
Lokalizacja: data/downloaders/download_trails_data.py
Uruchomienie:
    python data/downloaders/download_trails_data.py
"""

import sys
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

# Dołączenie głównego folderu projektu do sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
import geopandas as gpd
from shapely.geometry import LineString

from data.downloaders.terrain_downloader import TerrainDownloader, PRESETS

# Lista globalnych serwerów Overpass API z pełną bazą Polski
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
]


class TrailsDownloader:
    """
    Klasa odpowiedzialna za:
    - Pobieranie oficjalnych szlaków turystycznych PTTK i ścieżek górskich z OpenStreetMap.
    - Selektywne filtrowanie: szlaki turystyczne i ścieżki piesze zamiast wszystkich dróg leśnych.
    - Odporność na błędy serwerów Overpass API (rotacja serwerów globalnych, kafelkowanie, retry).
    - Transformację geometrii do układu metrycznego EPSG:2180 (zgodnego z siatką DEM).
    - Zapis geometrii szlaków do pliku GeoJSON.
    """

    def __init__(self, metric_crs: str = "EPSG:2180"):
        self.metric_crs = metric_crs

    def _query_overpass(self, query: str, max_retries: int = 3, timeout: int = 90) -> Dict[str, Any]:
        """Wysyła zapytanie Overpass QL z rotacją serwerów i obsługą ponawiania."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
            "Referer": "https://overpass-turbo.eu/",
            "Accept": "*/*"
        }

        last_error = None
        for endpoint in OVERPASS_ENDPOINTS:
            server_name = endpoint.split("/")[2]
            for attempt in range(1, max_retries + 1):
                try:
                    print(f"[*] Zapytanie do serwera {server_name} (próba {attempt}/{max_retries}, timeout {timeout}s)...")
                    resp = requests.post(
                        endpoint,
                        data={"data": query},
                        headers=headers,
                        timeout=timeout
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        elements = data.get("elements", [])
                        if len(elements) > 0:
                            return data
                        else:
                            print(f"    [!] Serwer {server_name} zwrócił 0 obiektów. Sprawdzam kolejny serwer...")
                            break
                    elif resp.status_code in [429, 502, 504]:
                        print(f"    [!] Serwer {server_name} zajęty (kod {resp.status_code}). Czekam...")
                        time.sleep(3.0 * attempt)
                    else:
                        print(f"    [!] Serwer {server_name} zwrócił kod: {resp.status_code}")
                        break
                except Exception as ex:
                    last_error = ex
                    print(f"    [!] Błąd połączenia z {server_name}: {ex}")
                    time.sleep(2.0)

            print(f"[*] Przełączanie na kolejny serwer Overpass...")

        raise RuntimeError(f"Wszystkie serwery Overpass API nie zwróciły danych. Ostatni błąd: {last_error}")

    def download_tourist_trails(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        include_all_tracks: bool = False
    ) -> gpd.GeoDataFrame:
        """
        Pobiera oficjalne szlaki turystyczne i ścieżki piesze.
        Najpierw próbuje pobrać cały obszar w jednym zapytaniu. W razie potrzeby dzieli na 4 sektory.
        """
        print(f"[*] Pobieranie oficjalnych szlaków turystycznych (relacje route=hiking/foot oraz highway=path)...")
        print(f"    Zakres BBox: lon [{min_lon:.4f}, {max_lon:.4f}], lat [{min_lat:.4f}, {max_lat:.4f}]")

        tracks_filter = 'way["highway"="track"]' if include_all_tracks else ''

        def build_ql(b_min_lat, b_min_lon, b_max_lat, b_max_lon):
            parts = [
                f'relation["route"~"hiking|foot"]({b_min_lat},{b_min_lon},{b_max_lat},{b_max_lon});',
                'way(r);',
                f'way["highway"="path"]({b_min_lat},{b_min_lon},{b_max_lat},{b_max_lon});'
            ]
            if include_all_tracks:
                parts.append(f'way["highway"="track"]({b_min_lat},{b_min_lon},{b_max_lat},{b_max_lon});')
            body = "\n  ".join(parts)
            return f"""[out:json][timeout:90];
(
  {body}
);
out geom;"""

        all_records = []
        seen_osm_ids = set()

        def parse_elements(elements):
            nonlocal all_records, seen_osm_ids
            added = 0
            for elem in elements:
                if elem.get("type") == "way" and "geometry" in elem:
                    osm_id = elem.get("id")
                    if osm_id in seen_osm_ids:
                        continue
                    seen_osm_ids.add(osm_id)

                    pts = elem["geometry"]
                    if len(pts) >= 2:
                        coords = [(pt["lon"], pt["lat"]) for pt in pts]
                        tags = elem.get("tags", {})
                        all_records.append({
                            "osm_id": str(osm_id),
                            "highway": str(tags.get("highway", "path")),
                            "name": str(tags.get("name", "")),
                            "surface": str(tags.get("surface", "")),
                            "tracktype": str(tags.get("tracktype", "")),
                            "geometry": LineString(coords)
                        })
                        added += 1
            return added

        # 1. Próba pobrania całego obszaru w jednym zapytaniu
        try:
            print("[*] Próba pobrania całościowego obszaru jednym zapytaniem...")
            full_ql = build_ql(min_lat, min_lon, max_lat, max_lon)
            data = self._query_overpass(full_ql, max_retries=2, timeout=90)
            elements = data.get("elements", [])
            added = parse_elements(elements)
            print(f"[+] Pobrano pomyślnie cały obszar! Znaleziono {added:,} unikalnych odcinków szlaków.")
        except Exception as e:
            print(f"[!] Zapytanie całościowe nie powiodło się ({e}). Przełączam na podział na 4 sektory...")
            mid_lon = (min_lon + max_lon) / 2.0
            mid_lat = (min_lat + max_lat) / 2.0
            tiles = [
                (min_lon, min_lat, mid_lon, mid_lat, "SW (Rabka-Zdrój / Nowy Targ)"),
                (mid_lon, min_lat, max_lon, mid_lat, "SE (Ochotnica / Lubań / Krościenko)"),
                (min_lon, mid_lat, mid_lon, max_lat, "NW (Mszana Dolna / Poręba Wielka)"),
                (mid_lon, mid_lat, max_lon, max_lat, "NE (Kamienica / Szczawa / Gorc)")
            ]
            for t_min_lon, t_min_lat, t_max_lon, t_max_lat, tile_name in tiles:
                print(f"\n[*] Sektor: {tile_name}")
                tile_ql = build_ql(t_min_lat, t_min_lon, t_max_lat, t_max_lon)
                try:
                    data = self._query_overpass(tile_ql, max_retries=2, timeout=60)
                    added = parse_elements(data.get("elements", []))
                    print(f"    -> Dodano {added:,} unikalnych odcinków z tego sektora.")
                except Exception as ex_tile:
                    print(f"    [!] Błąd sektora {tile_name}: {ex_tile}")

        if not all_records:
            print("[!] Nie znaleziono żadnych szlaków turystycznych.")
            return gpd.GeoDataFrame(columns=["highway", "name", "surface", "tracktype", "length", "geometry"], crs=self.metric_crs)

        # Utworzenie GeoDataFrame w WGS84
        gdf_wgs84 = gpd.GeoDataFrame(all_records, crs="EPSG:4326")
        print(f"\n[*] Łącznie pozyskano {len(gdf_wgs84):,} odcinków szlaków.")

        # Transformacja do układu metrycznego EPSG:2180 (PUWG 1992)
        print(f"[*] Reprojekcja geometrii szlaków do układu metrycznego: {self.metric_crs}...")
        gdf_metric = gdf_wgs84.to_crs(self.metric_crs)
        gdf_metric["length"] = gdf_metric.geometry.length.round(2)

        return gdf_metric

    def save_trails_geojson(self, gdf: gpd.GeoDataFrame, output_path: str):
        """Zapisuje GeoDataFrame szlaków do pliku GeoJSON."""
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_file(str(out_file), driver="GeoJSON")
        print(f"[+] Szlaki turystyczne zapisane pomyślnie w pliku: {out_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Pobieranie szlaków turystycznych PTTK i ścieżek górskich z OSM dla GOPR."
    )
    parser.add_argument(
        "--preset",
        type=str,
        default="gopr-gorce",
        choices=["gopr-gorce"],
        help="Profil obszaru operacyjnego (domyślnie: 'gopr-gorce')"
    )
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
        default=None,
        help="Opcjonalny własny zakres BBox: min_lon min_lat max_lon max_lat"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Ścieżka do pliku wyjściowego GeoJSON (domyślnie: data/trails/gorce_trails.geojson)"
    )
    parser.add_argument(
        "--all-tracks",
        action="store_true",
        default=False,
        help="Włącza również wszystkie drogi gospodarcze (uwaga: może spowodować zagęszczenie)"
    )

    args = parser.parse_args()

    output_path = Path(args.output) if args.output else PROJECT_ROOT / "data" / "trails" / "gorce_trails.geojson"
    area_display = "Rejon Operacyjny Grupy Podhalańskiej GOPR - Gorce" if not args.bbox else f"Własny BBox {args.bbox}"

    print("=" * 80)
    print(" POBIERANIE SZLAKÓW TURYSTYCZNYCH I ŚCIEŻEK GÓRSKICH (OVERPASS / OSM)")
    print("=" * 80)
    print(f" Obszar:           {area_display}")
    print(f" Plik docelowy:    {output_path}")
    print(f" Tryb:             Szlaki PTTK + ścieżki górskie {'(+ wszystkie drogi leśne)' if args.all_tracks else ''}")
    print(f" Układ metryczny:  EPSG:2180 (PUWG 1992)")
    print("=" * 80)

    if args.bbox:
        min_lon, min_lat, max_lon, max_lat = args.bbox
    else:
        cfg = PRESETS[args.preset]
        min_lon, min_lat, max_lon, max_lat = cfg["min_lon"], cfg["min_lat"], cfg["max_lon"], cfg["max_lat"]

    trails_downloader = TrailsDownloader(metric_crs="EPSG:2180")
    trails_gdf = trails_downloader.download_tourist_trails(
        min_lon=min_lon,
        min_lat=min_lat,
        max_lon=max_lon,
        max_lat=max_lat,
        include_all_tracks=args.all_tracks
    )

    trails_downloader.save_trails_geojson(trails_gdf, str(output_path))

    # Podsumowanie statystyczne
    total_len_km = trails_gdf["length"].sum() / 1000.0 if not trails_gdf.empty else 0.0
    print("\n" + "=" * 80)
    print(" PODSUMOWANIE POBRANYCH SZLAKÓW:")
    print(f" - Łączna liczba odcinków:  {len(trails_gdf):,}")
    print(f" - Łączna długość szlaków:   {total_len_km:.2f} km")
    if "highway" in trails_gdf.columns:
        print(" - Podział według kategorii:")
        counts = trails_gdf["highway"].value_counts()
        for hw_type, count in counts.head(6).items():
            print(f"    * {hw_type:15s}: {count:,} odcinków")
    print("=" * 80)
    print(" Następny krok: Zbuduj graf terenu ze szlakami:")
    print(" -> python data/mappers/build_terrain_graph.py")
    print("=" * 80)


if __name__ == "__main__":
    main()
