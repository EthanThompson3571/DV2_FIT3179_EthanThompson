from pathlib import Path
import pandas as pd
import requests

BASE = Path(__file__).resolve().parent
DATA = BASE / "Datasets V2"

SOURCE = DATA / "chart3_sa3_consumption.csv"
OUTPUT = DATA / "chart3_sa3_with_coordinates.csv"

SERVICE = (
    "https://geo.abs.gov.au/arcgis/rest/services/"
    "ASGS2021/SA3/MapServer"
)

wanted = [
    "Cereals and cereal products",
    "Milk products and dishes",
    "Vegetable products and dishes",
    "Fruit products and dishes",
    "Cereal based products and dishes",
    "Fats and oils",
    "Fish and seafood products and dishes",
    "Meat, poultry and game products and dishes"
]

session = requests.Session()


def get_json(url, params):
    response = session.get(
        url,
        params=params,
        timeout=120
    )
    response.raise_for_status()

    data = response.json()

    if "error" in data:
        raise RuntimeError(str(data["error"]))

    return data


def main():

    df = pd.read_csv(
        SOURCE,
        dtype={"sa3_code": str}
    )

    df["sa3_code"] = (
        df["sa3_code"]
        .str.strip()
        .str.zfill(5)
    )

    df = df[df["food_group"].isin(wanted)].copy()

    df["grams_per_10000kj"] = pd.to_numeric(
        df["grams_per_10000kj"],
        errors="coerce"
    )

    df = df.dropna(
        subset=["grams_per_10000kj"]
    )

    print("Consumption regions:", df.sa3_code.nunique())

    # Inspect available ABS geographical layers
    service_info = get_json(
        SERVICE,
        {"f": "json"}
    )

    layers = service_info.get("layers", [])

    print("\nAvailable geographical layers:")

    for layer in layers:
        print(layer["id"], layer["name"])

    # Find a layer containing SA3 codes
    chosen = None

    for layer in layers:

        layer_id = layer["id"]

        metadata = get_json(
            f"{SERVICE}/{layer_id}",
            {"f": "json"}
        )

        fields = [
            field["name"]
            for field in metadata.get("fields", [])
        ]

        code_fields = [
            name for name in fields
            if "SA3" in name.upper()
            and "CODE" in name.upper()
        ]

        if code_fields:
            chosen = {
                "id": layer_id,
                "code_field": code_fields[0],
                "fields": fields,
                "metadata": metadata
            }
            break

    if chosen is None:
        raise RuntimeError(
            "Could not find an SA3 code field "
            "in the ABS service."
        )

    layer_id = chosen["id"]
    code_field = chosen["code_field"]

    print("\nSelected layer:", layer_id)
    print("SA3 code field:", code_field)

    # Request the identifiers for all features
    query_url = f"{SERVICE}/{layer_id}/query"

    id_response = get_json(
        query_url,
        {
            "where": "1=1",
            "returnIdsOnly": "true",
            "f": "json"
        }
    )

    object_ids = id_response.get("objectIds", [])

    if not object_ids:
        raise RuntimeError(
            "No geographical features returned."
        )

    print("Geographical features:", len(object_ids))

    coordinates = []

    # Download features in batches
    for start in range(0, len(object_ids), 100):

        batch = object_ids[start:start + 100]

        result = get_json(
            query_url,
            {
                "objectIds": ",".join(map(str, batch)),
                "outFields": code_field,
                "returnGeometry": "true",
                "returnCentroid": "true",
                "outSR": 4326,
                "f": "json"
            }
        )

        for feature in result.get("features", []):

            attrs = feature.get("attributes", {})

            raw_code = attrs.get(code_field)

            if raw_code is None:
                continue

            code = str(raw_code).strip().zfill(5)

            centre = feature.get("centroid")

            # Use geometry extent as a fallback
            if not centre:

                geometry = feature.get("geometry", {})

                rings = geometry.get("rings", [])

                points = [
                    point
                    for ring in rings
                    for point in ring
                ]

                if not points:
                    continue

                lon = (
                    min(p[0] for p in points) +
                    max(p[0] for p in points)
                ) / 2

                lat = (
                    min(p[1] for p in points) +
                    max(p[1] for p in points)
                ) / 2

            else:
                lon = centre["x"]
                lat = centre["y"]

            if not (
                105 <= lon <= 170
                and -46 <= lat <= -9
            ):
                continue

            coordinates.append({
                "sa3_code": code,
                "longitude": lon,
                "latitude": lat
            })

    locations = pd.DataFrame(coordinates)

    if locations.empty:
        raise RuntimeError(
            "No valid coordinates returned."
        )

    locations = locations.drop_duplicates(
        "sa3_code"
    )

    print(
        "Unique geographical codes:",
        locations.sa3_code.nunique()
    )

    print(
        "Sample geographical codes:",
        locations.sa3_code.head(5).tolist()
    )

    print(
        "Sample consumption codes:",
        df.sa3_code.head(5).tolist()
    )

    joined = df.merge(
        locations,
        on="sa3_code",
        how="left",
        validate="many_to_one"
    )

    matched = joined[
        joined["longitude"].notna()
    ]["sa3_code"].nunique()

    print("\nMatched SA3 regions:", matched)
    print("Total consumption regions:", df.sa3_code.nunique())

    if matched == 0:
        raise RuntimeError(
            "No matching SA3 codes. "
            "Check the printed code samples and layer."
        )

    joined = joined.dropna(
        subset=["longitude", "latitude"]
    )

    joined.to_csv(OUTPUT, index=False)

    print("\nSUCCESS!")
    print("Saved:", OUTPUT)
    print("Rows:", len(joined))


if __name__ == "__main__":
    main()
