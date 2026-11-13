# Symulacja Akcji Ratunkowych GOPR - Model Terenu i Agentów

## Moduł Topografii i Siatki Terenu 3D

Wszystkie narzędzia związane z pozyskiwaniem danych, budową siatki terenu oraz wizualizacją 3D znajdują się wyłącznie w podkatalogach katalogu `data/`:

```text
               Krok 1                                    Krok 2                                     Krok 3
┌──────────────────────────────────────┐     ┌────────────────────────────────────┐     ┌────────────────────────────────────────┐
│ data/downloaders/                    │     │ data/mappers/                      │     │ data/visualizers/                      │
│ download_terrain_data.py             │     │ build_terrain_graph.py             │     │ visualize_terrain_3d.py                │
│                                      │     │                                    │     │                                        │
│ - Granice z OSM (GeoJSON)            │     │ - Wczytuje JSON (OFFLINE)          │     │ - Wczytuje GraphML (OFFLINE)           │
│ - Siatka w układzie PUWG 1992        │────>│ - Buduje graf 2D/3D (8 kierunków)  │────>│ - Interaktywny model WebGL 3D (HTML)   │
│ - Rzędne DEM bez limitu (retry 429)  │     │ - Liczy nachylenia stoku (stopnie) │     │ - Render 3D stoku (PNG)                │
│ - Zapis do terrain_points.json       │     │ - Zapisuje .graphml                │     │ - Opcjonalne okno desktopowe 3D        │
└──────────────────────────────────────┘     └────────────────────────────────────┘     └────────────────────────────────────────┘
```

---

### Instrukcja uruchomienia krok po kroku

#### 1. Pobieranie danych geograficznych (`data/downloaders/`)
Pobiera granice obszaru z OpenStreetMap oraz rzędne wysokościowe z modelu Copernicus DEM 30m (lub z lokalnego pliku GeoTIFF).
* **Brak limitu czasowego**: Cierpliwe ponawianie prób przy ograniczeniach serwera (HTTP 429).
* **Ciągły zapis cache**: Każda partia punktów jest natychmiast utrwalana na dysku w `data/dem/elevation_cache.json`.

```bash
# Pobranie danych Gorczańskiego Parku Narodowego (krok siatki 100 m):
python data/downloaders/download_terrain_data.py --step 100

# Szybki test siatki o mniejszej gęstości (krok 250 m):
python data/downloaders/download_terrain_data.py --step 250
```

#### 2. Budowa grafu rzeźby terenu (`data/mappers/`)
Działa **w 100% offline**. Wczytuje plik `data/dem/terrain_points.json`, łączy punkty w siatkę o 8-kierunkowym sąsiedztwie i dla każdej krawędzi wylicza:
* `distance_2d` [m] – rzut poziomy
* `elevation_change` [m] – przewyższenie ($dz$)
* `distance_3d` [m] – rzeczywistą długość marszu w przestrzeni 3D
* `slope_degrees` [°] – kąt nachylenia stoku (-90° do +90°)
* `slope_ratio` – tangens kąta stoku
* `grade_pct` [%] – nachylenie procentowe

```bash
python data/mappers/build_terrain_graph.py
```

#### 3. Wizualizacja i eksploracja 3D (`data/visualizers/`)
Działa **w 100% offline**. Wczytuje wygenerowany graf `data/trails/gorce_terrain_grid.graphml` i tworzy:
1. **Interaktywny model 3D WebGL (`data/trails/gorce_terrain_3d.html`)**: Samodzielny plik HTML do otwarcia w dowolnej przeglądarce internetowej (Chrome, Edge, Firefox). Umożliwia swobodny obrót myszką 360°, płynny zoom rolką, przesuwanie kamery, przełączanie siatki krawędzi (Wireframe) oraz wyświetla panel informacyjny HUD.
2. **Statyczny obraz 3D (`data/trails/gorce_3d_terrain.png`)**: Trójwymiarowy render stoku z hipsometryczną paletą barw.

```bash
# Generuje model HTML oraz obraz PNG:
python data/visualizers/visualize_terrain_3d.py

# Opcjonalnie otwiera okno 3D na pulpicie:
python data/visualizers/visualize_terrain_3d.py --show
```

---

## Struktura Katalogów Projektu

```text
Agentowa_symulacja_akcji_ratunkowych/
├── config/                      # Pliki konfiguracyjne symulacji (YAML / JSON)
├── data/                        # Wszystkie dane GIS oraz narzędzia przetwarzania terenu
│   ├── dem/                     # Rzędne wysokościowe i cache
│   │   ├── elevation_cache.json # Lokalny cache punktów wysokościowych (Open-Meteo)
│   │   └── terrain_points.json  # Punkty terenu z rzędnymi (x, y, z)
│   ├── trails/                  # Wygenerowane grafy i wizualizacje
│   │   ├── gorce_terrain_grid.graphml # Graf topograficzny terenu
│   │   ├── gorce_terrain_3d.html      # Interaktywny model 3D WebGL
│   │   ├── gorce_3d_terrain.png       # Statyczny render 3D
│   │   └── park_boundary.geojson      # Granice obszaru
│   ├── downloaders/             # Narzędzia pobierania danych (Program 1)
│   │   ├── terrain_downloader.py      # Klasa TerrainDownloader
│   │   └── download_terrain_data.py   # Skrypt uruchomieniowy CLI
│   ├── mappers/                 # Narzędzia budowy grafu (Program 2)
│   │   ├── terrain_mapper.py          # Klasa TerrainGraphMapper
│   │   └── build_terrain_graph.py     # Skrypt uruchomieniowy CLI
│   └── visualizers/             # Narzędzia wizualizacji 3D (Program 3)
│       ├── terrain_visualizer.py      # Moduł renderujący Three.js i Matplotlib
│       └── visualize_terrain_3d.py    # Skrypt uruchomieniowy CLI
├── notebooks/                   # Notatniki Jupyter (.ipynb)
├── src/                         # Moduły symulacji
│   ├── core/                    # Silnik DES + ABM w SimPy (ratownicy, dyspozytor, incydenty)
│   ├── routing/                 # Warstwa trasowania ratowników (routing_interface, mock_routing)
│   ├── sar/                     # Poszukiwania Search & Rescue
│   └── metrics/                 # Metryki efektywności i czasy dotarcia
├── tests/                       # Testy jednostkowe (pytest)
│   ├── test_rescuer.py
│   └── test_terrain_graph.py
├── environment.yml              # Konfiguracja środowiska Conda
└── README.md                    # Dokumentacja projektu
```
