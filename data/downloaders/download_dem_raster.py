#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Automatyczny skrypt pobierający satelitarny Numeryczny Model Terenu (Copernicus DEM 30m).
Pobiera publiczne kafelki GeoTIFF z rejestru ESA/AWS Open Data dla rejonu Gorców i GOPR,
łączy je i zapisuje zoptymalizowany raster do data/dem/gorce_dem.tif.

Uruchomienie:
    python data/downloaders/download_dem_raster.py
"""

import sys
import time
import shutil
import urllib.request
from pathlib import Path
from typing import List, Tuple

import rasterio
from rasterio.merge import merge
from rasterio.mask import mask
import shapely.geometry as geom

# Dołączenie głównego folderu projektu do sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Publiczne kafelki Copernicus GLO-30 na AWS Open Data (brak limitów zapytań)
COPERNICUS_TILES = [
    {
        "name": "Kafelek Zachodni (E019: Rabka-Zdrój, Turbacz Zachód)",
        "url": "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com/Copernicus_DSM_COG_10_N49_00_E019_00_DEM/Copernicus_DSM_COG_10_N49_00_E019_00_DEM.tif",
        "filename": "copernicus_N49_E019.tif"
    },
    {
        "name": "Kafelek Wschodni (E020: Turbacz Szczyt, Gorc, Lubań, Krościenko)",
        "url": "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com/Copernicus_DSM_COG_10_N49_00_E020_00_DEM/Copernicus_DSM_COG_10_N49_00_E020_00_DEM.tif",
        "filename": "copernicus_N49_E020.tif"
    }
]

# Obszar Gorców i terenu działań GOPR z marginesem
# Lon: 19.85E do 20.55E, Lat: 49.42N do 49.72N
GORCE_CROP_BOX = geom.box(19.85, 49.42, 20.55, 49.72)


def download_file_with_progress(url: str, output_path: Path, title: str):
    """Pobiera plik ze wskazaniem postępu w konsoli."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.is_file() and output_path.stat().st_size > 1024 * 1024:
        print(f"[*] {title}: plik już istnieje w pamięci podręcznej ({output_path.stat().st_size / (1024*1024):.1f} MB), pomijam pobieranie.")
        return

    print(f"[*] Rozpoczynam pobieranie: {title}...")
    start_time = time.time()

    def reporthook(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            pct = min(100.0, (downloaded / total_size) * 100.0)
            mb_down = downloaded / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            elapsed = time.time() - start_time
            speed = mb_down / elapsed if elapsed > 0 else 0
            sys.stdout.write(f"\r    -> Pobrano: {mb_down:.1f} MB / {mb_total:.1f} MB ({pct:.1f}%) | Prędkość: {speed:.1f} MB/s")
            sys.stdout.flush()

    req = urllib.request.Request(url, headers={"User-Agent": "GOPR-Simulation-Terrain/1.0"})
    temp_path = output_path.with_suffix(".tmp")
    with urllib.request.urlopen(req, timeout=60) as resp, open(temp_path, "wb") as f_out:
        total_size = int(resp.headers.get("Content-Length", 0))
        block_size = 1024 * 256
        block_num = 0
        while True:
            chunk = resp.read(block_size)
            if not chunk:
                break
            f_out.write(chunk)
            block_num += 1
            reporthook(block_num, block_size, total_size)

    temp_path.replace(output_path)
    print(f"\n    -> Zakończono pobieranie kafelka ({output_path.stat().st_size / (1024*1024):.1f} MB).")


def merge_and_crop_tiles(tile_paths: List[Path], output_dem_path: Path):
    """Łączy kafelki GeoTIFF i wycina precyzyjny wycinek dla terenu Gorców."""
    print("\n[*] Łączenie i przycinanie kafelków GeoTIFF dla rejonu Gorców...")
    src_files = [rasterio.open(p) for p in tile_paths]

    try:
        # 1. Scalenie kafelków (merge)
        mosaic, out_trans = merge(src_files)
        out_meta = src_files[0].meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": mosaic.shape[1],
            "width": mosaic.shape[2],
            "transform": out_trans,
            "crs": src_files[0].crs,
            "compress": "deflate"
        })

        # Zapis tymczasowej mozaiki
        temp_merged = output_dem_path.parent / "temp_merged.tif"
        with rasterio.open(temp_merged, "w", **out_meta) as dest:
            dest.write(mosaic)

        # 2. Przycięcie do granic rejonu Gorców (mask/crop)
        print("[*] Przycinanie do dokładnego obszaru Gorców i baz GOPR...")
        with rasterio.open(temp_merged) as src_merged:
            out_image, out_transform = mask(src_merged, [GORCE_CROP_BOX], crop=True)
            crop_meta = src_merged.meta.copy()
            crop_meta.update({
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
                "compress": "deflate"
            })

            output_dem_path.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(output_dem_path, "w", **crop_meta) as final_dest:
                final_dest.write(out_image)

        if temp_merged.is_file():
            temp_merged.unlink()

        final_mb = output_dem_path.stat().st_size / (1024 * 1024)
        print(f"\n" + "=" * 80)
        print(f" SUKCES! Gotowy Numeryczny Model Terenu (DEM) zapisany w:")
        print(f" -> {output_dem_path} ({final_mb:.1f} MB)")
        print(f" Rozdzielczość: 30 metrów na piksel (Copernicus DEM GLO-30)")
        print(f" Zakres: Całe pasmo Gorców od Rabki po Krościenko i od Mszany po Nowy Targ.")
        print(f"=" * 80)

    finally:
        for f in src_files:
            f.close()


def ensure_dem_raster(output_dem_path: Optional[Path] = None) -> Path:
    """
    Zapewnia dostępność lokalnego rastra numerycznego modelu terenu (gorce_dem.tif).
    Jeśli plik już istnieje, natychmiast zwraca ścieżkę do niego.
    W przeciwnym razie automatycznie pobiera kafelki satelitarne i tworzy gotowy raster.
    """
    if output_dem_path is None:
        output_dem_path = PROJECT_ROOT / "data" / "dem" / "gorce_dem.tif"

    if output_dem_path.is_file() and output_dem_path.stat().st_size > 1024 * 1024:
        return output_dem_path

    print(f"[*] Nie znaleziono lokalnego pliku NMT: {output_dem_path}")
    print("[*] Rozpoczynam automatyczne pobieranie kafelków Copernicus DEM 30m z AWS...")

    cache_dir = output_dem_path.parent / "cache_tiles"
    downloaded_paths = []
    for tile in COPERNICUS_TILES:
        dest_path = cache_dir / tile["filename"]
        download_file_with_progress(tile["url"], dest_path, tile["name"])
        downloaded_paths.append(dest_path)

    merge_and_crop_tiles(downloaded_paths, output_dem_path)
    return output_dem_path


def main():
    print("=" * 80)
    print(" AUTOMATYCZNY POBIERACZ NUMERYCZNEGO MODELU TERENU (COPERNICUS DEM 30M)")
    print("=" * 80)

    output_dem = PROJECT_ROOT / "data" / "dem" / "gorce_dem.tif"
    ensure_dem_raster(output_dem)

    print("\nMożesz teraz błyskawicznie wygenerować siatkę terenu GOPR w ułamku sekundy:")
    print("-> python data/downloaders/download_terrain_data.py --preset gopr-gorce --step 100")


if __name__ == "__main__":
    main()
