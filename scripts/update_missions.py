    elif authoritative_feed and penny_ok:
        # A valid structured response with zero V-Bucks missions is still
        # a successful live check, but do not erase previously confirmed
        # mission data based on an empty parse.
        today_missions = _recover_today(old, history_days, today)
        confirmed = False
        status = "partial" if source_reachable else "unavailable"

    else:
        today_missions = _recover_today(
            old, history_days, today
        )
        confirmed = False
        status = "partial" if source_reachable else "unavailable"

    today_missions = _deduplicate(today_missions)

    archive_record = {
        "date": today,
        "checkedAt": now,
        "confirmed": confirmed,
        "missions": today_missions,
        "sourceSummaries": [
            {
                "name": source["name"],
                "url": source["url"],
                "ok": source["ok"],
                "summary": source.get("summary", {}),
                "missionCount": source.get("missionCount", 0),
                "powerLevelCount": source.get("powerLevelCount", 0),
                "locationCount": source.get("locationCount", 0),
                "status": source.get("status", "No status"),
            }
            for source in source_results
        ],
    }

    existing_index = next(
        (
            i for i, item in enumerate(history_days)
            if item.get("date") == today
        ),
        None,
    )

    if existing_index is None:
        history_days.append(archive_record)

    else:
        prior = history_days[existing_index]

        if confirmed or not prior.get("confirmed"):
            history_days[existing_index] = archive_record

        else:
            prior["checkedAt"] = now
            prior["sourceSummaries"] = archive_record[
                "sourceSummaries"
            ]

    history_days = sorted(
        history_days,
        key=lambda item: item.get("date", ""),
    )[-400:]

    history_output = {
        "updatedAt": now,
        "days": history_days,
    }

    output = {
        "updatedAt": now,
        "confirmed": confirmed,
        "status": status,
        "today": today_missions,
        "yesterday": _yesterday_missions(
            old, history_days, today
        ),
        "sources": source_results,
        "historyDays": len(history_days),
        "historyAvailable": bool(history_days),
    }

    DATA.mkdir(parents=True, exist_ok=True)

    MISSIONS_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    HISTORY_FILE.write_text(
        json.dumps(history_output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    power_count = sum(
        item.get("powerLevel") is not None
        for item in today_missions
    )

    location_count = sum(
        bool(item.get("location"))
        for item in today_missions
    )

    print(
        f"Checked {len(source_results)} source(s); "
        f"{sum(bool(source.get('ok')) for source in source_results)} reachable; "
        f"{len(today_missions)} mission rows; "
        f"{power_count} rows with source-provided Power Levels; "
        f"{location_count} rows with source-provided locations; "
        f"source={'PennyDB structured API' if authoritative_feed else 'HTML fallback / archive'}; "
        f"{len(history_days)} archived days."
    )

    if not source_reachable:
        sys.exit(
            "All live mission sources failed; preserved any last "
            "confirmed data without inventing missions or Power Levels."
        )


if __name__ == "__main__":
    main()
