def parse_pennydb_payload(payload: Any) -> list[dict[str, Any]]:
    """Parse PennyDB missions and print raw data for location debugging."""

    if not isinstance(payload, dict) or not isinstance(
        payload.get("missions"), dict
    ):
        raise ValueError("PennyDB response is missing the missions object")

    raw_zones = payload["missions"]
    recognized_zone_arrays = 0
    parsed: list[dict[str, Any]] = []

    for raw_zone, entries in raw_zones.items():
        zone = _zone_name(raw_zone)

        if zone is None:
            continue

        if not isinstance(entries, list):
            raise ValueError(
                f"PennyDB zone {raw_zone!r} is not a list"
            )

        recognized_zone_arrays += 1

        for raw_mission in entries:
            if not isinstance(raw_mission, dict):
                continue

            # TEMPORARY DEBUG: show actual PennyDB mission fields.
            quantity = _mission_vbucks_amount(raw_mission)

            if quantity is not None:
                print(
                    "\n========== PENNYDB MISSION DEBUG =========="
                )
                print("ZONE:", zone)
                print(
                    json.dumps(
                        raw_mission,
                        indent=2,
                        ensure_ascii=False
                    )
                )
                print(
                    "========== END MISSION DEBUG ==========\n"
                )

            if quantity is None:
                continue

            mission_name = _mission_name(
                raw_mission.get("missionType")
            )

            if not mission_name:
                continue

            location = _mission_location(raw_mission)

            item: dict[str, Any] = {
                "mission": mission_name,
                "zone": zone,
                "location": location,
                "vbucks": quantity,
                "source": "PennyDB",
                "sources": ["PennyDB"],
            }

            power_level = _valid_power_level(
                raw_mission.get("pl")
            )

            if power_level is not None:
                item["powerLevel"] = power_level

            parsed.append(item)

    if recognized_zone_arrays == 0:
        raise ValueError(
            "PennyDB response did not contain recognized Save the World zones"
        )

    return _deduplicate(parsed)
