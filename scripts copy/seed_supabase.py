#!/usr/bin/env python3
"""
seed_supabase.py — Load data/seed/*.json into Supabase (idempotent upserts).

Usage:
    python scripts/seed_supabase.py

Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env or environment.
"""
import json
import os
import sys

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from transithear.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ENABLED

if not SUPABASE_ENABLED:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
    sys.exit(1)

from supabase import create_client  # type: ignore

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

SEED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "seed")


def load_seed(filename: str) -> list:
    path = os.path.join(SEED_DIR, filename)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        data.pop("_note", None)
        for v in data.values():
            if isinstance(v, list):
                return v
    return []


def upsert(table: str, rows: list, conflict_col: str) -> int:
    if not rows:
        print(f"  {table}: no rows to insert")
        return 0
    # Convert None arr/dep to string or remove
    result = sb.table(table).upsert(rows, on_conflict=conflict_col).execute()
    return len(result.data or [])


def main():
    print("TransitHear Supabase Seeder")
    print("=" * 40)

    # Stations
    stations = load_seed("stations.json")
    n = upsert("stations", stations, "code")
    print(f"  stations:    {n}/{len(stations)} upserted")

    # Trains
    trains = load_seed("trains.json")
    n = upsert("trains", trains, "number")
    print(f"  trains:      {n}/{len(trains)} upserted")

    # Train stops
    stops = load_seed("train_stops.json")
    # Convert None times to null-safe strings
    for stop in stops:
        for key in ("arr", "dep"):
            if stop.get(key) is None:
                stop[key] = None
    n = upsert("train_stops", stops, "train_number,seq")
    print(f"  train_stops: {n}/{len(stops)} upserted")

    # Facilities
    facilities = load_seed("facilities.json")
    n = upsert("facilities", facilities, "id")
    print(f"  facilities:  {n}/{len(facilities)} upserted")

    # Alternatives
    alternatives = load_seed("alternatives.json")
    n = upsert("alternatives", alternatives, "id")
    print(f"  alternatives:{n}/{len(alternatives)} upserted")

    print("=" * 40)
    print("Done. Supabase seeded successfully.")


if __name__ == "__main__":
    main()
