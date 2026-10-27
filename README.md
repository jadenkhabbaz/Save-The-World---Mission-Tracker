# Save the World V-Bucks Mission Tracker — automatic archive edition

Unofficial fan-made project. Not affiliated with or endorsed by Epic Games.

## What this version does

- GitHub Actions checks four public Save the World tracker pages every 30 minutes.
- Stores source availability, source-reported historical V-Bucks summary totals, and timestamps in `public/data/missions.json`.
- Maintains a dated snapshot archive in `public/data/history.json` (up to 400 days).
- Saves individual mission rows only when a public page exposes enough information to identify a mission, zone, and reward. It does not invent mission data or turn an unavailable source into a false zero.
- The browser displays each source's status and source-reported history separately from the tracker’s own daily snapshots.

## Repository layout

Keep `wrangler.jsonc` in the repository root, alongside `public/`, `.github/`, and `scripts/`.

```text
wrangler.jsonc
public/
  index.html
  app.js
  style.css
  vbucks-logo.png
  data/
    missions.json
    history.json
scripts/
  update_missions.py
.github/
  workflows/
    update.yml
```

## Setup

1. Upload the contents of this extracted project to the root of the GitHub repository, preserving the folders above.
2. In GitHub, open **Settings → Actions → General → Workflow permissions** and allow read and write permissions if the repository settings require it. The workflow also declares `contents: write`.
3. Open **Actions → Update Save the World mission archive → Run workflow** to test it once.
4. The scheduled job runs every 30 minutes. Successful data commits can trigger Cloudflare Workers Builds to publish the updated JSON with the site.
5. In Cloudflare, the build command should be `npx wrangler deploy`, and the root directory should be the repository root (blank/default). `wrangler.jsonc` expects static assets in `./public`.

## Historical data limitations

Third-party websites expose different amounts of history. This project imports visible source summary totals when parsable, but cannot recreate old individual mission names/rewards for dates when a source did not publish or expose those records. Individual rows are archived from the first successful scrape onward. If a site changes its HTML, the source status will show the fetch/parser issue rather than claiming the missions are zero.

## Sources checked

- https://hawkbucks.com/vbucks-missions
- https://vbucksdaily.com/
- https://savetheworlddb.com/
- https://v2.fortnitedb.com/

The sites are independent third-party sources. Confirm rewards in-game before playing.
