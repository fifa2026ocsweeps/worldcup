# ⚽ Soccer World Cup 2026 – OC Sweepstakes

Live at: **https://fifa2026ocsweeps.github.io/worldcup**

## Setup (one-time, ~10 minutes)

### 1. Create GitHub Organisation
1. Go to https://github.com/organizations/plan
2. Choose **Free** plan
3. Name it exactly: `fifa2026ocsweeps`

### 2. Create the repository
1. Inside the org, create a new **public** repo named `worldcup`
2. Don't initialise with any files

### 3. Push this code
```bash
cd ~/worldcup
git init
git add .
git commit -m "Initial deploy – FIFA 2026 Sweepstakes"
git remote add origin https://github.com/fifa2026ocsweeps/worldcup.git
git branch -M main
git push -u origin main
```

### 4. Enable GitHub Pages
1. Repo → **Settings** → **Pages**
2. Source: **GitHub Actions**
3. The `deploy.yml` workflow will publish automatically on every push

### 5. Add API keys as Secrets (for live daily updates)
Go to: Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret name | Where to get it | Free tier |
|---|---|---|
| `ODDS_API_KEY` | https://the-odds-api.com | 500 req/month ✅ |
| `FOOTBALL_DATA_KEY` | https://www.football-data.org/client/register | Free tier ✅ |

> ⚠️ Both keys are **optional** – if not set, the page falls back to static pre-tournament data.

### 6. Test the workflow manually
Repo → **Actions** → **Update Live Standings** → **Run workflow**

---

## How it works

| Tab | Content | Updates |
|---|---|---|
| 📋 Sweepstakes Draw | Who drew which teams | Never (static) |
| 📊 Team Odds | Win probability for all 48 teams | Never (pre-tournament snapshot) |
| 🏅 Player Standings | Player rankings based on pre-tournament odds | Never (static) |
| 🔴 Live Standings | Player rankings based on current odds | **Daily at 4pm AEST** |

The daily update workflow (`update.yml`):
- Runs at **06:00 UTC** = 4:00 PM AEST
- Fetches latest outright winner odds from The Odds API
- Fetches the last finished match from football-data.org
- Recomputes player win probabilities
- Commits updated `data.json` → triggers a fresh deploy

---

## File structure
```
worldcup/
├── index.html                        ← Single-page app (all 4 tabs)
├── data.json                         ← Live data (auto-updated daily)
├── scripts/
│   └── update_odds.py                ← Odds fetcher + standings calculator
└── .github/workflows/
    ├── deploy.yml                    ← Deploys to GitHub Pages on push
    └── update.yml                    ← Runs daily at 4pm AEST
```
