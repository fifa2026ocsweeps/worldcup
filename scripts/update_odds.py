#!/usr/bin/env python3
"""
FIFA 2026 World Cup – Daily odds & standings updater
Runs via GitHub Actions every day at 4pm AEST (06:00 UTC).

Required GitHub Secrets:
  ODDS_API_KEY        – from https://the-odds-api.com (free tier: 500 req/month)
  FOOTBALL_DATA_KEY   – from https://www.football-data.org (free tier)
"""

import json
import os
import sys
import requests
from datetime import datetime, timezone

# ─── User draw data ───────────────────────────────────────────────────────────
DRAW = [
    {"name": "Liam Carter",       "teams": ["Jordan", "Mexico", "Bahrain"]},
    {"name": "Olivia Bennett",    "teams": ["Argentina", "Cape Verde"]},
    {"name": "Noah Patel",        "teams": ["Bahrain"]},
    {"name": "Emma Rossi",        "teams": ["Cameroon"]},
    {"name": "James Müller",      "teams": ["Sweden", "Australia", "New Zealand"]},
    {"name": "Sophia Tanaka",     "teams": ["Canada", "Mexico"]},
    {"name": "Lucas Ferreira",    "teams": ["Ghana"]},
    {"name": "Ava Kowalski",      "teams": ["Belgium"]},
    {"name": "Ethan Nguyen",      "teams": ["Mexico", "Türkiye", "Tunisia"]},
    {"name": "Isabella García",   "teams": ["Senegal", "DR Congo", "Sweden"]},
    {"name": "Mason Okonkwo",     "teams": ["Cape Verde", "Norway"]},
    {"name": "Amelia Johansson",  "teams": ["Colombia", "United States", "Egypt"]},
    {"name": "Logan Dubois",      "teams": ["Croatia", "England", "Colombia"]},
    {"name": "Charlotte Kim",     "teams": ["Ghana"]},
    {"name": "Alexander Petrov",  "teams": ["Iran", "Australia"]},
    {"name": "Mia Svensson",      "teams": ["Iran", "France"]},
    {"name": "Henry Nakamura",    "teams": ["Costa Rica", "Brazil"]},
    {"name": "Harper Silva",      "teams": ["Iraq"]},
    {"name": "Jack O'Brien",      "teams": ["Sweden", "Jordan"]},
    {"name": "Aria Andersen",     "teams": ["Australia", "Türkiye"]},
    {"name": "Sebastian Reyes",   "teams": ["Honduras", "Panama"]},
    {"name": "Evelyn Hasan",      "teams": ["Czechia", "Tunisia"]},
    {"name": "Owen Marchetti",    "teams": ["South Korea", "Canada", "Côte d'Ivoire"]},
    {"name": "Luna Ivanova",      "teams": ["Uruguay"]},
    {"name": "Felix Bergmann",    "teams": ["Cape Verde"]},
]

# Fallback static probabilities (used if API calls fail)
FALLBACK_PROBS = {
    "Spain": 17.4, "France": 16.7, "England": 13.3, "Brazil": 10.5,
    "Argentina": 10.0, "Portugal": 9.1, "Germany": 6.7, "Netherlands": 4.3,
    "Belgium": 2.8, "Norway": 2.8, "Colombia": 2.4, "Uruguay": 1.9,
    "Morocco": 1.9, "United States": 1.6, "Switzerland": 1.5, "Japan": 1.5,
    "Mexico": 1.2, "Croatia": 1.2, "Ecuador": 1.2, "Senegal": 1.1,
    "Türkiye": 0.99, "Turkey": 0.99, "Sweden": 0.99, "Austria": 0.66,
    "Canada": 0.50, "Scotland": 0.50, "Côte d'Ivoire": 0.40, "Ivory Coast": 0.40,
    "Czechia": 0.40, "Paraguay": 0.33, "Egypt": 0.33, "Ghana": 0.33,
    "Algeria": 0.29, "South Korea": 0.25, "Bosnia & Herzegovina": 0.20,
    "Tunisia": 0.20, "Australia": 0.17, "Iran": 0.14, "DR Congo": 0.10,
    "Congo DR": 0.10, "Saudi Arabia": 0.10, "South Africa": 0.10,
    "Panama": 0.10, "Cape Verde": 0.10, "Cameroon": 0.10, "Costa Rica": 0.08,
    "Qatar": 0.07, "Uzbekistan": 0.07, "New Zealand": 0.07, "Iraq": 0.07,
    "Jordan": 0.04, "Curaçao": 0.04, "Haiti": 0.04, "Bahrain": 0.04,
    "Honduras": 0.04,
}

# Normalise team names returned by various APIs to our canonical names
TEAM_ALIASES = {
    "turkey": "Türkiye", "turkiye": "Türkiye",
    "ivory coast": "Côte d'Ivoire", "cote d'ivoire": "Côte d'Ivoire",
    "dr congo": "DR Congo", "congo dr": "DR Congo", "democratic republic of congo": "DR Congo",
    "usa": "United States", "united states of america": "United States",
    "south korea": "South Korea", "republic of korea": "South Korea",
    "bosnia and herzegovina": "Bosnia & Herzegovina",
    "curacao": "Curaçao",
}

def normalise(name):
    return TEAM_ALIASES.get(name.lower().strip(), name.strip())


# ─── Fetch odds from The Odds API ────────────────────────────────────────────
def fetch_team_probs(api_key):
    """Return dict {team_name: probability_%} from The Odds API outright market."""
    url = "https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds/"
    params = {
        "apiKey": api_key,
        "regions": "uk,eu",
        "markets": "outrights",
        "oddsFormat": "decimal",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[WARN] Odds API error: {e}", file=sys.stderr)
        return None

    # Aggregate decimal odds per team across bookmakers (use average)
    team_odds_sum = {}
    team_odds_count = {}

    for event in data:
        for bm in event.get("bookmakers", []):
            for market in bm.get("markets", []):
                if market.get("key") != "outrights":
                    continue
                for outcome in market.get("outcomes", []):
                    team = normalise(outcome["name"])
                    decimal_odds = float(outcome["price"])
                    team_odds_sum[team] = team_odds_sum.get(team, 0) + decimal_odds
                    team_odds_count[team] = team_odds_count.get(team, 0) + 1

    if not team_odds_sum:
        return None

    # Convert average decimal odds → implied probability, then normalise to 100%
    raw = {t: 1 / (team_odds_sum[t] / team_odds_count[t]) * 100
           for t in team_odds_sum}
    total = sum(raw.values())
    return {t: round(v / total * 100, 2) for t, v in raw.items()}


# ─── Fetch last finished match from football-data.org ────────────────────────
def fetch_last_match(api_key):
    """Return a human-readable string for the most recently finished WC match."""
    url = "https://api.football-data.org/v4/competitions/WC2026/matches"
    headers = {"X-Auth-Token": api_key}
    params = {"status": "FINISHED"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        matches = r.json().get("matches", [])
        if not matches:
            return "No matches played yet"
        last = matches[-1]
        home = last["homeTeam"]["name"]
        away = last["awayTeam"]["name"]
        hs = last["score"]["fullTime"]["home"]
        as_ = last["score"]["fullTime"]["away"]
        date = last["utcDate"][:10]
        stage = last.get("stage", "").replace("_", " ").title()
        return f"{stage}: {home} {hs}–{as_} {away}  ({date})"
    except Exception as e:
        print(f"[WARN] football-data.org error: {e}", file=sys.stderr)
        return "Match data unavailable"


# ─── Compute player standings ─────────────────────────────────────────────────
def compute_players(team_probs):
    players = []
    for p in DRAW:
        prob = sum(team_probs.get(t, FALLBACK_PROBS.get(t, 0.05)) for t in p["teams"])
        players.append({"name": p["name"], "teams": p["teams"], "probability": round(prob, 2)})
    players.sort(key=lambda x: x["probability"], reverse=True)
    return players


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    odds_key = os.environ.get("ODDS_API_KEY", "")
    fd_key   = os.environ.get("FOOTBALL_DATA_KEY", "")

    # Fetch live odds (or fall back to static)
    team_probs = None
    source = "Pre-tournament static data (live odds API not configured)"

    if odds_key:
        print("Fetching live odds from The Odds API…")
        team_probs = fetch_team_probs(odds_key)
        if team_probs:
            source = "The Odds API (live betting markets)"
            print(f"  Got odds for {len(team_probs)} teams.")
        else:
            print("  Failed – falling back to static data.")

    if team_probs is None:
        team_probs = FALLBACK_PROBS.copy()

    # Fetch last match
    last_match = "Tournament not yet started"
    if fd_key:
        print("Fetching last match from football-data.org…")
        last_match = fetch_last_match(fd_key)
        print(f"  Last match: {last_match}")

    # Build output
    players = compute_players(team_probs)
    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_match": last_match,
        "source": source,
        "players": players,
    }

    out_path = os.path.join(os.path.dirname(__file__), "..", "data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"✅  data.json updated – {len(players)} players written.")


if __name__ == "__main__":
    main()
