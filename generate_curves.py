import csv
import json
import math

INPUT = "Datasets V2/aus_food_import_flows_2023.csv"
OUTPUT = "Datasets V2/curved_food_flows.geojson"

features = []

with open(INPUT, newline="", encoding="utf-8-sig") as f:
    rows = csv.DictReader(f)

    for row in rows:
        lon1 = float(row["source_lon"])
        lat1 = float(row["source_lat"])
        lon2 = float(row["target_lon"])
        lat2 = float(row["target_lat"])

        # Create a curved route using a quadratic Bezier curve.
        dx = lon2 - lon1
        dy = lat2 - lat1

        mid_lon = (lon1 + lon2) / 2
        mid_lat = (lat1 + lat2) / 2

        # Perpendicular offset creates the bend.
        length = math.hypot(dx, dy)
        bend = min(length * 0.18, 18)

        control_lon = mid_lon - dy / length * bend
        control_lat = mid_lat + dx / length * bend

        coordinates = []

        for i in range(61):
            t = i / 60

            lon = (
                (1 - t)**2 * lon1
                + 2 * (1 - t) * t * control_lon
                + t**2 * lon2
            )

            lat = (
                (1 - t)**2 * lat1
                + 2 * (1 - t) * t * control_lat
                + t**2 * lat2
            )

            coordinates.append([lon, lat])

        features.append({
            "type": "Feature",
            "properties": {
                "partner": row["partner"],
                "import_usd_million": float(
                    row["import_usd_million"]
                )
            },
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates
            }
        })

geojson = {
    "type": "FeatureCollection",
    "features": features
}

with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(geojson, f)

print("Created:", OUTPUT)
