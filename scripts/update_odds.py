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
    {"name": "Steph",         "teams": ["Canada"]},
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
    {"name": "Clarence",      "teams": ["Cape Verde"]},
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
    try:
        r = requests.get(
            "https://api.the-odds-api.com/v4/sports/",
            params={"apiKey": api_key, "all": "true"},
            timeout=15,
        )
        r.raise_for_status()
        sports = r.json()
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
    sport_key = find_wc_sport_key(api_key)
    if not sport_key:
        print("[WARN] FIFA World Cup sport not found in The Odds API.", file=sys.stderr)
        return None

    print(f"  Using sport key: {sport_key}")
    for market in ("outrights", "h2h"):
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
        params = {"apiKey": api_key, "regions": "uk,eu,us", "markets": market, "oddsFormat": "decimal"}
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

    team_odds_sum, team_odds_count = {}, {}
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

    raw = {t: 1 / (team_odds_sum[t] / team_odds_count[t]) * 100 for t in team_odds_sum}
    total = sum(raw.values())
    return {t: round(v / total * 100, 2) for t, v in raw.items()}


# ─── Fetch last finished match ────────────────────────────────────────────────
def fetch_last_match(headers):
    url = "https://api.football-data.org/v4/competitions/WC/matches"
    try:
        r = requests.get(url, headers=headers, params={"status": "FINISHED", "season": "2026"}, timeout=15)
        r.raise_for_status()
        matches = r.json().get("matches", [])
        if not matches:
            return "No matches played yet"
        last = matches[-1]
        home = last["homeTeam"]["name"]
        away = last["awayTeam"]["name"]
        hs   = last["score"]["fullTime"]["home"]
        as_  = last["score"]["fullTime"]["away"]
        date = last["utcDate"][:10]
        stage = last.get("stage", "").replace("_", " ").title()
        return f"{stage}: {home} {hs}–{as_} {away}  ({date})"
    except Exception as e:
        print(f"[WARN] Last match fetch error: {e}", file=sys.stderr)
        return "Match data unavailable"


# ─── Fetch team stats from group standings ───────────────────────────────────
def fetch_team_stats(headers):
    """Return dict keyed by team name with group stage stats."""
    url = "https://api.football-data.org/v4/competitions/WC/standings"
    try:
        r = requests.get(url, headers=headers, params={"season": "2026"}, timeout=15)
        r.raise_for_status()
        standings = r.json().get("standings", [])
        team_stats = {}
        for group in standings:
            group_name = group.get("group", group.get("stage", "Group"))
            for entry in group.get("table", []):
                name = normalise(entry["team"]["name"])
                team_stats[name] = {
                    "group":        group_name,
                    "played":       entry.get("playedGames", 0),
                    "won":          entry.get("won", 0),
                    "drawn":        entry.get("draw", 0),
                    "lost":         entry.get("lost", 0),
                    "goals_for":    entry.get("goalsFor", 0),
                    "goals_against":entry.get("goalsAgainst", 0),
                    "goal_diff":    entry.get("goalDifference", 0),
                    "points":       entry.get("points", 0),
                }
        print(f"  ✅ Team stats fetched for {len(team_stats)} teams.")
        return team_stats
    except Exception as e:
        print(f"[WARN] Standings fetch error: {e}", file=sys.stderr)
        return {}


# ─── Fetch next fixture per team ─────────────────────────────────────────────
def fetch_next_fixtures(headers, team_stats):
    """Add next_fixture string to each team in team_stats dict."""
    url = "https://api.football-data.org/v4/competitions/WC/matches"
    try:
        r = requests.get(url, headers=headers,
                         params={"status": "SCHEDULED", "season": "2026"}, timeout=15)
        r.raise_for_status()
        scheduled = r.json().get("matches", [])

        # Build lookup: team_name → next match string
        next_fix = {}
        for m in scheduled:
            home = normalise(m["homeTeam"]["name"])
            away = normalise(m["awayTeam"]["name"])
            date_str = m["utcDate"][:10]
            stage = m.get("stage", "").replace("_", " ").title()
            fixture_str = f"{stage}: {home} vs {away} ({date_str})"
            for team in (home, away):
                if team not in next_fix:  # only store first (soonest) fixture
                    next_fix[team] = fixture_str

        for team in team_stats:
            team_stats[team]["next_fixture"] = next_fix.get(team, "No upcoming fixture")

        print(f"  ✅ Next fixtures mapped for {len(next_fix)} teams.")
    except Exception as e:
        print(f"[WARN] Fixtures fetch error: {e}", file=sys.stderr)
        for team in team_stats:
            team_stats[team].setdefault("next_fixture", "Unavailable")

    return team_stats


# ─── Fetch top scorers ────────────────────────────────────────────────────────
def fetch_top_scorers(headers, limit=5):
    url = "https://api.football-data.org/v4/competitions/WC/scorers"
    try:
        r = requests.get(url, headers=headers,
                         params={"season": "2026", "limit": limit}, timeout=15)
        r.raise_for_status()
        scorers = r.json().get("scorers", [])
        result = []
        for s in scorers:
            result.append({
                "name":   s["player"]["name"],
                "team":   normalise(s["team"]["name"]),
                "goals":  s.get("goals", 0),
                "assists":s.get("assists", 0),
            })
        print(f"  ✅ Top {len(result)} scorers fetched.")
        return result
    except Exception as e:
        print(f"[WARN] Scorers fetch error: {e}", file=sys.stderr)
        return []


# ─── Derive tournament highlights from team stats ────────────────────────────
def compute_highlights(team_stats, top_scorers):
    if not team_stats:
        return {}

    by_gf = sorted(team_stats.items(), key=lambda x: x[1].get("goals_for", 0),    reverse=True)
    by_ga = sorted(team_stats.items(), key=lambda x: x[1].get("goals_against", 0), reverse=True)

    highlights = {}
    if by_gf and by_gf[0][1].get("goals_for", 0) > 0:
        highlights["top_scoring_team"] = {
            "team":  by_gf[0][0],
            "goals": by_gf[0][1]["goals_for"],
        }
    if by_ga and by_ga[0][1].get("goals_against", 0) > 0:
        highlights["most_conceded_team"] = {
            "team":  by_ga[0][0],
            "goals": by_ga[0][1]["goals_against"],
        }
    if top_scorers:
        highlights["top_scorers"] = top_scorers

    return highlights


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

    print("=" * 50)
    print(f"ODDS_API_KEY     : {'SET ✅' if odds_key else 'NOT SET ❌'}")
    print(f"FOOTBALL_DATA_KEY: {'SET ✅' if fd_key else 'NOT SET ❌'}")
    print("=" * 50)

    fd_headers = {"X-Auth-Token": fd_key} if fd_key else {}

    # ── Win probabilities ──────────────────────────────────────────────────────
    team_probs = None
    source = "Pre-tournament static data (live odds API not configured)"

    if odds_key:
        print("\nFetching live odds from The Odds API…")
        team_probs = fetch_team_probs(odds_key)
        if team_probs:
            source = "The Odds API (live betting markets)"
            print(f"  ✅ Got odds for {len(team_probs)} teams.")
        else:
            print("  ⚠️  Falling back to static probabilities.")
            source = "Static fallback (Odds API unavailable)"
    else:
        print("\n⚠️  ODDS_API_KEY not set — using static probabilities.")

    if team_probs is None:
        team_probs = FALLBACK_PROBS.copy()

    # ── Last match ────────────────────────────────────────────────────────────
    last_match = "Tournament not yet started"
    if fd_key:
        print("\nFetching last match…")
        last_match = fetch_last_match(fd_headers)
        print(f"  {last_match}")
    else:
        print("\n⚠️  FOOTBALL_DATA_KEY not set — skipping match/stats fetch.")

    # ── Team stats, fixtures, scorers ─────────────────────────────────────────
    team_stats  = {}
    highlights  = {}
    if fd_key:
        print("\nFetching group standings…")
        team_stats = fetch_team_stats(fd_headers)

        if team_stats:
            print("Fetching next fixtures…")
            team_stats = fetch_next_fixtures(fd_headers, team_stats)

            print("Fetching top scorers…")
            top_scorers = fetch_top_scorers(fd_headers)
            highlights  = compute_highlights(team_stats, top_scorers)

    # ── Build output ──────────────────────────────────────────────────────────
    players = compute_players(team_probs)
    output = {
        "last_updated":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_match":    last_match,
        "source":        source,
        "players":       players,
        "team_stats":    team_stats,
        "highlights":    highlights,
    }

    out_path = os.path.join(os.path.dirname(__file__), "..", "data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅  data.json written — {len(players)} players, {len(team_stats)} team stats, highlights: {list(highlights.keys())}")


if __name__ == "__main__":
    main()
