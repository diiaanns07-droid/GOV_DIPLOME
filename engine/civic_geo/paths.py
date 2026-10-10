"""Пути к данным (только чтение графа; свои данные R12 — в data/civic/astana/geo/)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GRAPHS_DIR = ROOT / "engine" / "civic_scenarios" / "graphs"
GRAPH_ID = "osm-astana-walking-20260506"
GEO_DIR = ROOT / "data" / "civic" / "astana" / "geo"
OSM_OBJECTS_DIR = ROOT / "data" / "civic" / "astana" / "osm-objects"
OSM_WALKING_RAW = ROOT / "data" / "civic" / "astana" / "osm-walking" / "overpass.json.gz"
GEOFENCE = ROOT / "data" / "civic" / "astana" / "geofence.json"
DEMO_SYNTHETIC = ROOT / "data" / "civic" / "astana" / "demo_synthetic.json"
# Источник истины по категориям (CONTRACT §3): не копируем список в код, а читаем файл.
CATEGORIES = ROOT / "research" / "round-14" / "categories_v2.json"
WEB_MAP_DIR = ROOT / "web" / "civic" / "map"
