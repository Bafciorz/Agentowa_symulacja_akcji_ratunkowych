# Symulacja Akcji Ratunkowych GOPR - Model Terenu i Agentów

## Moduł Topografii, Siatki Terenu 3D i Szlaków Turystycznych

Wszystkie narzędzia związane z pozyskiwaniem danych, budową siatki terenu, integracją szlaków oraz wizualizacją 3D znajdują się wyłącznie w podkatalogach katalogu `data/`:

```text
               Krok 1                                    Krok 2                                     Krok 3
┌──────────────────────────────────────┐     ┌────────────────────────────────────┐     ┌────────────────────────────────────────┐
│ data/downloaders/                    │     │ data/mappers/                      │     │ data/visualizers/                      │
│ - download_terrain_data.py (NMT/DEM) │     │ build_terrain_graph.py             │     │ visualize_terrain_3d.py                │
│ - download_trails_data.py  (Szlaki)  │     │                                    │     │                                        │
│                                      │     │ - Wczytuje DEM JSON i szlaki       │     │ - Wczytuje GraphML (OFFLINE)           │
│ - Granice z OSM (GeoJSON)            │────>│ - Buduje graf 2D/3D (8 kierunków)  │────>│ - Interaktywny model WebGL 3D (HTML)   │
│ - Siatka w układzie PUWG 1992        │     │ - Rzutuje szlaki na siatkę terenu  │     │ - Podświetlenie szlaków na CZERWONO    │
│ - Rzędne DEM (Copernicus 30m)        │     │ - Liczy wagi Toblera + opór terenu │     │ - Swobodny obrót 360°, zoom, wireframe │
│ - Szlaki i drogi leśne z OSM         │     │ - Zapisuje .graphml                │     │                                        │
└──────────────────────────────────────┘     └────────────────────────────────────┘     └────────────────────────────────────────┘
```

---

### Instrukcja uruchomienia krok po kroku

#### Krok 0. (Zalecany) Błyskawiczny satelitarny raster DEM (`data/downloaders/download_dem_raster.py`)
Pobiera publiczne kafelki numerycznego modelu terenu **Copernicus DEM 30m (GLO-30)** z rejestru AWS Open Data / ESA, łączy je i przycina do terenu Gorców jako plik `data/dem/gorce_dem.tif`.
* **Koniec z limitami HTTP 429**: Pobranie kafelków GeoTIFF zajmuje ~5-10 sekund (brak jakichkolwiek limitów zapytań).
* **Błyskawiczne próbkowanie**: Program do budowy siatki terenu automatycznie wykrywa `data/dem/gorce_dem.tif` i próbkuje nawet **95 000 punktów wysokościowych w ułamku sekundy** całkowicie offline za pomocą biblioteki `rasterio`.

```bash
# Jednorazowe pobranie rastra satelitarnego dla całych Gorców:
python data/downloaders/download_dem_raster.py
```

#### 1a. Pobieranie siatki wysokościowej terenu (`data/downloaders/download_terrain_data.py`)
Generuje regularną siatkę punktów dla **całego rejonu operacyjnego GOPR w Gorcach** (od Rabki po Krościenko i od Mszany po Nowy Targ) oraz przypisuje rzędne wysokościowe z modelu satelitarnego Copernicus DEM 30m (`data/dem/gorce_dem.tif`).

```bash
# Domyślne pobranie całego terenu operacyjnego GOPR (siatka co 100 m):
python data/downloaders/download_terrain_data.py --step 100

# Opcja lżejszej siatki (np. co 200 m dla szybszego przetestowania):
python data/downloaders/download_terrain_data.py --step 200
```

#### 1b. Pobieranie szlaków turystycznych i dróg leśnych (`data/downloaders/download_trails_data.py`)
Pobiera rzeczywistą sieć szlaków turystycznych (pieszych, górskich i dróg leśnych) z bazy OpenStreetMap (OSM) za pomocą biblioteki `osmnx` i transformuje je do układu metrycznego EPSG:2180.

```bash
# Pobranie szlaków dla profilu Gorców (do pliku data/trails/gorce_trails.geojson):
python data/downloaders/download_trails_data.py
```

#### 2. Budowa grafu rzeźby terenu i integracja szlaków (`data/mappers/build_terrain_graph.py`)
Działa **w 100% offline**. Wczytuje punkty `data/dem/terrain_points.json` oraz szlaki `data/trails/gorce_trails.geojson`, łączy punkty w siatkę o 8-kierunkowym sąsiedztwie i dla każdej krawędzi wylicza:
* `distance_2d` [m] – rzut poziomy
* `elevation_change` [m] – przewyższenie ($dz$)
* `distance_3d` [m] – rzeczywistą długość marszu w przestrzeni 3D
* `slope_degrees` [°] – kąt nachylenia stoku (-90° do +90°)
* `slope_ratio` – tangens kąta stoku
* `is_trail` – flaga logiczna (czy krawędź leży w korytarzu szlaku turystycznego)
* `surface_friction` – współczynnik oporu podłoża ($1.0$ dla szlaku, $4.0$ dla terenu pozaszlakowego)
* `speed_kmh` – efektywną prędkość marszu ratownika wg **funkcji Toblera** z uwzględnieniem oporu podłoża
* `travel_time_min` / `weight` – fizyczny czas pokonania krawędzi w minutach (waga dla algorytmów trasowania)

```bash
python data/mappers/build_terrain_graph.py
```

#### 3. Wizualizacja i eksploracja 3D ze szlakami (`data/visualizers/visualize_terrain_3d.py`)
Działa **w 100% offline**. Wczytuje wygenerowany graf `data/trails/gorce_terrain_grid.graphml` i tworzy **interaktywny model 3D WebGL (`data/trails/gorce_terrain_3d.html`)**:
* **Szlaki na czerwono**: Węzły i krawędzie w korytarzu szlaków turystycznych są wyraźnie wyróżnione intensywnym **czerwonym kolorem**.
* Samodzielny, lekki plik HTML do otwarcia w dowolnej przeglądarce internetowej (Chrome, Edge, Firefox).
* Umożliwia swobodny obrót myszką 360°, płynny zoom rolką, przesuwanie kamery oraz przełączanie siatki krawędzi (Wireframe) i widoczności szlaków.
* Zawiera dyskretny panel informacyjny z parametrami terenu i statystykami szlaków.

```bash
# Generuje interaktywny model HTML:
python data/visualizers/visualize_terrain_3d.py
```

---

## Struktura Katalogów Projektu

```text
Agentowa_symulacja_akcji_ratunkowych/
├── config/                      # Pliki konfiguracyjne symulacji (YAML / JSON)
├── data/                        # Wszystkie dane GIS oraz narzędzia przetwarzania terenu
│   ├── dem/                     # Rzędne wysokościowe i raster
│   │   ├── gorce_dem.tif        # Sklejony i przycięty satelitarny raster GeoTIFF (Copernicus DEM 30m)
│   │   └── terrain_points.json  # Punkty terenu z rzędnymi (x, y, z)
│   ├── trails/                  # Wygenerowane grafy i wizualizacje
│   │   ├── gorce_trails.geojson       # Geometrie szlaków turystycznych i dróg leśnych z OSM
│   │   ├── gorce_terrain_grid.graphml # Graf topograficzny terenu ze szlakami i wagami Toblera
│   │   ├── gorce_terrain_3d.html      # Interaktywny model 3D WebGL z czerwonymi szlakami
│   │   └── gopr_boundary.geojson      # Granice obszaru operacyjnego GOPR
│   ├── downloaders/             # Narzędzia pobierania danych (Program 1)
│   │   ├── download_dem_raster.py     # Pobieracz satelitarnego rastra GeoTIFF (Copernicus DEM)
│   │   ├── terrain_downloader.py      # Klasa TerrainDownloader
│   │   ├── download_terrain_data.py   # Skrypt CLI siatki wysokościowej terenu
│   │   └── download_trails_data.py    # Skrypt CLI pobierania szlaków turystycznych z OSM
│   ├── mappers/                 # Narzędzia budowy grafu (Program 2)
│   │   ├── terrain_mapper.py          # Klasa TerrainGraphMapper (siatka + szlaki + Tobler)
│   │   └── build_terrain_graph.py     # Skrypt CLI budowy grafu z oporem podłoża
│   └── visualizers/             # Narzędzia wizualizacji 3D (Program 3)
│       ├── terrain_visualizer.py      # Moduł renderujący Three.js (szlaki podświetlone na czerwono)
│       └── visualize_terrain_3d.py    # Skrypt uruchomieniowy CLI wizualizacji 3D
├── notebooks/                   # Notatniki Jupyter (.ipynb)
├── src/                         # Moduły symulacji
│   ├── core/                    # Silnik DES + ABM w SimPy (ratownicy, dyspozytor, incydenty)
│   ├── routing/                 # Warstwa trasowania ratowników (routing_interface, mock_routing)
│   ├── sar/                     # Poszukiwania Search & Rescue
│   └── metrics/                 # Metryki efektywności i czasy dotarcia
├── tests/                       # Testy jednostkowe (pytest)
│   ├── test_rescuer.py
│   ├── test_team_coordination.py
│   └── test_terrain_graph.py
├── environment.yml              # Konfiguracja środowiska Conda
└── README.md                    # Dokumentacja projektu
```
