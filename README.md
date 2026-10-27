# STW V-Bucks Tracker

A small, mobile-friendly Fortnite Save the World V-Bucks mission tracker.

## Important: live data setup

The site UI is ready, but it does **not** automatically receive live V-Bucks Daily data out of the box. I could not verify a public, authorized JSON/API feed from V-Bucks Daily. This project deliberately avoids scraping its HTML without permission.

The daily workflow expects a permitted HTTPS JSON endpoint configured as the GitHub Actions repository secret `STW_DATA_URL`. That endpoint should return a JSON object such as:

```json
{
  "confirmed": true,
  "note": "Mission feed checked",
  "missions": [
    {
      "mission": "Fight the Storm",
      "zone": "Stonewood",
      "location": "City",
      "powerLevel": 5,
      "vbucks": 50,
      "expiresAt": "2026-10-28T00:00:00Z"
    }
  ]
}
```

You must confirm the data source's terms allow automated reuse. If V-Bucks Daily offers a public feed or grants permission, use that endpoint. If its data is only available as webpage HTML, ask the site owner for permission or choose another authorized source. Do not use login cookies, private credentials, or bypass anti-bot protections.

## Test locally

Python 3 is optional for a local web server. From this folder:

```bash
python -m http.server 8000
```

Open `http://localhost:8000`.

## Configure automatic updates

1. Push this folder to a GitHub repository.
2. Open the repository's **Settings → Secrets and variables → Actions**.
3. Add a repository secret named `STW_DATA_URL` containing the authorized HTTPS JSON feed URL.
4. Open **Actions → Update STW mission data → Run workflow** to test it.
5. The scheduled job runs daily at 00:10 UTC. GitHub scheduled jobs can be delayed, so the refresh is not guaranteed to happen at the exact minute.
6. Connect the repository to Cloudflare Pages. Use the repository root as the project, build command `exit 0`, and output directory `.`.

## Deployment

Cloudflare Pages supports static HTML. See:
https://developers.cloudflare.com/pages/framework-guides/deploy-anything/

## Notes

- A mission alert's listed reward is not a promise that every account is eligible.
- Confirm mission rewards in the game before launching.
- V-Bucks Daily is an independent site; this project is not affiliated with it or Epic Games.
