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
    {"name": "Matt",          "teams": ["Argentina"]},
    {"name": "Livia",         "teams": ["France"]},
    {"name": "Alan",          "teams": ["Spain"]},
    {"name": "Jon",           "teams": ["England"]},
    {"name": "Gabi",          "teams": ["Brazil"]},
    {"name": "MEJ (Michael)", "teams": ["Portugal"]},
    {"name": "Orgil",         "teams": ["Netherlands"]},
    {"name": "Rose",          "teams": ["Belgium", "Uzbekistan"]},
    {"name": "Georgia",       "teams": ["Germany"]},
    {"name": "Mark",          "teams": ["Morocco"]},
    {"name": "Denis",         "teams": ["Croatia"]},
    {"name": "Pip",           "teams": ["Uruguay"]},
    {"name": "Alistair",      "teams": ["Colombia"]},
    {"name": "Aditi",         "teams": ["Japan"]},
    {"name": "Jimmy",         "teams": ["United States", "Qatar"]},
    {"name": "Marcelo",       "teams": ["Mexico"]},
    {"name": "Lach",          "teams": ["Senegal"]},
    {"name": "Tess",          "teams": ["Switzerland"]},
    {"name": "Jamaica",       "teams": ["Iran"]},
    {"name": "Anita",         "teams": ["Austria"]},
    {"name": "Sanaz",         "teams": ["South Korea"]},
    {"name": "Sarah",         "teams": ["Australia"]},
    {"name": "Linda",         "teams": ["Ecuador", "Bosnia & Herzegovina"]},
    {"name": "Adele",         "teams": ["Türkiye"]},
    {"name": "Lidia",         "teams": ["Sweden"]},
    {"name": "Steph",         "teams": ["Cape Verde"]},
    {"name": "Fiona",         "teams": ["Panama"]},
    {"name": "Kena",          "teams": ["Egypt"]},
    {"name": "Nicko",         "teams": ["Algeria"]},
    {"name": "Kash",          "teams": ["Czechia"]},
    {"name": "Jodie",         "teams": ["Côte d'Ivoire"]},
    {"name": "Eden",          "teams": ["Norway"]},
    {"name": "Simon D",       "teams": ["Scotland"]},
    {"name": "Reino",         "teams": ["Paraguay"]},
    {"name": "Dani",          "teams": ["Tunisia"]},
    {"name": "Lids",          "teams": ["South Africa"]},
    {"name": "Cristina",      "teams": ["New Zealand"]},
    {"name": "Amy",           "teams": ["Curaçao"]},
    {"name": "Kath",          "teams": ["DR Congo"]},
    {"name": "Upendra",       "teams": ["Haiti"]},
    {"name": "Gina",          "teams": ["Jordan"]},
    {"name": "Clarence",      "teams": ["Canada"]},
    {"name": "Daniel",        "teams": ["Saudi Arabia"]},
    {"name": "Maria",         "teams": ["Iraq"]},
    {"name": "Josh",          "teams": ["Ghana"]},
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


# ─── Discover correct FIFA WC sport key from The Odds API ────────────────────
def find_wc_sport_key(api_key):
    """Return the sport key for FIFA World Cup outright winner market, or None."""
    try:
        r = requests.get(
            "https://api.the-odds-api.com/v4/sports/",
            params={"apiKey": api_key, "all": "true"},
            timeout=15,
        )
        r.raise_for_status()
        sports = r.json()
        # Prefer an outright/winner market; fall back to any WC sport
        wc_key = None
        for s in sports:
            key = s.get("key", "").lower()
            if "world_cup" in key and "winner" in key:
                return s["key"]
            if "world_cup" in key:
                wc_key = s["key"]
        if wc_key:
            print(f"  No winner-specific key found, using: {wc_key}")
        return wc_key
    except Exception as e:
        print(f"[WARN] Could not list sports: {e}", file=sys.stderr)
        return None


# ─── Fetch odds from The Odds API ────────────────────────────────────────────
def fetch_team_probs(api_key):
    """Return dict {team_name: probability_%} from The Odds API outright market."""
    sport_key = find_wc_sport_key(api_key)
    if not sport_key:
        print("[WARN] FIFA World Cup sport not found in The Odds API — not active yet?", file=sys.stderr)
        return None

    print(f"  Using sport key: {sport_key}")

    # Try outright winner market first, fall back to h2h
    for market in ("outrights", "h2h"):
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
        params = {
            "apiKey": api_key,
            "regions": "uk,eu,us",
            "markets": market,
            "oddsFormat": "decimal",
        }
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 422:
                print(f"  Market '{market}' not available, trying next…")
                continue
            r.raise_for_status()
            data = r.json()
            if data:
                print(f"  Got odds via market '{market}' for {len(data)} event(s).")
                break
        except Exception as e:
            print(f"[WARN] Odds API error ({market}): {e}", file=sys.stderr)
            return None
    else:
        return None

    # Aggregate decimal odds per team across bookmakers (use average)
    team_odds_sum = {}
    team_odds_count = {}

    for event in data:
        for bm in event.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                for outcome in mkt.get("outcomes", []):
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
    # Competition code is 'WC'; season=2026 targets the 2026 tournament
    url = "https://api.football-data.org/v4/competitions/WC/matches"
    headers = {"X-Auth-Token": api_key}
    params = {"status": "FINISHED", "season": "2026"}
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
