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
import time
import requests
from datetime import datetime, timezone, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def make_session():
    """HTTP session with automatic retries and backoff."""
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=2,          # waits 2, 4, 8 seconds between retries
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

SESSION = make_session()

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
    "bosnia-herzegovina": "Bosnia & Herzegovina",       # football-data.org uses hyphen
    "cape verde islands": "Cape Verde",                 # football-data.org full name
    "curacao": "Curaçao",
    "ir iran": "Iran",
    "korea republic": "South Korea",
    "czechia": "Czechia",
}

def normalise(name):
    if not name:
        return name
    return TEAM_ALIASES.get(name.lower().strip(), name.strip())


# ─── Discover correct FIFA WC sport key from The Odds API ────────────────────
def find_wc_sport_key(api_key):
    try:
        r = SESSION.get(
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
            r = SESSION.get(url, params=params, timeout=15)
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
        r = SESSION.get(url, headers=headers, params={"status": "FINISHED", "season": "2026"}, timeout=15)
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
def fetch_team_stats(headers, prev_stats=None):
    """Return dict keyed by team name with group stage stats.
    Falls back to prev_stats during knockout rounds when standings disappear."""
    url = "https://api.football-data.org/v4/competitions/WC/standings"
    try:
        r = SESSION.get(url, headers=headers, params={"season": "2026"}, timeout=15)
        r.raise_for_status()
        data = r.json()
        standings = data.get("standings", [])

        team_stats = {}
        for group in standings:
            # group field can be null or "GROUP_A" etc; stage is fallback
            raw_group  = group.get("group") or group.get("stage") or "Group Stage"
            # Prettify: "GROUP_A" → "Group A"
            group_name = raw_group.replace("_", " ").title()
            for entry in group.get("table", []):
                name = normalise(entry["team"]["name"])
                team_stats[name] = {
                    "group":         group_name,
                    "played":        entry.get("playedGames", 0),
                    "won":           entry.get("won", 0),
                    "drawn":         entry.get("draw", 0),
                    "lost":          entry.get("lost", 0),
                    "goals_for":     entry.get("goalsFor", 0),
                    "goals_against": entry.get("goalsAgainst", 0),
                    "goal_diff":     entry.get("goalDifference", 0),
                    "points":        entry.get("points", 0),
                }

        if team_stats:
            print(f"  ✅ Team stats fetched for {len(team_stats)} teams.")
            return team_stats

        # Empty standings = knockout stage or pre-tournament; preserve last known data
        if prev_stats:
            print("  ⚠️  Standings empty (knockout stage?). Preserving previous group stats.")
            return prev_stats

        print("  ⚠️  Standings empty and no previous data to fall back on.")
        return {}

    except Exception as e:
        print(f"[WARN] Standings fetch error: {e}", file=sys.stderr)
        return prev_stats or {}


# ─── Compute team stats from finished match results ──────────────────────────
def compute_stats_from_matches(all_matches, team_stats):
    """
    1. Patch goals_for/against/played/won/drawn/lost/points when standings lag.
    2. Always compute yellow_cards + red_cards per team from match bookings.
    """
    finished = [m for m in all_matches if m.get("status") == "FINISHED"]
    if not finished:
        return team_stats

    # ── Group assignment — extract from match group field (standings API returns null) ─
    team_group = {}
    for m in all_matches:
        raw_g = m.get("group") or ""
        if not raw_g or raw_g.upper() in ("GROUP_STAGE", ""):
            continue
        group_name = raw_g.replace("_", " ").title()  # "GROUP_A" → "Group A"
        home = normalise(m.get("homeTeam", {}).get("name"))
        away = normalise(m.get("awayTeam", {}).get("name"))
        if home: team_group[home] = group_name
        if away: team_group[away] = group_name
    if team_group:
        for team, g in team_group.items():
            if team in team_stats:
                team_stats[team]["group"] = g
        print(f"  ✅ Group assignments extracted from match data for {len(team_group)} teams.")

    # ── Goals / results — always compute from match results (standings API lags) ─
    print(f"  Computing goal/result stats from {len(finished)} finished matches...")
    computed = {}
    for m in finished:
        home = normalise(m.get("homeTeam", {}).get("name"))
        away = normalise(m.get("awayTeam", {}).get("name"))
        score = m.get("score", {}).get("fullTime", {})
        hg = score.get("home") or 0
        ag = score.get("away") or 0
        if not home or not away:
            continue
        for team, gf, ga in [(home, hg, ag), (away, ag, hg)]:
            if team not in computed:
                computed[team] = {"played": 0, "won": 0, "drawn": 0, "lost": 0,
                                  "goals_for": 0, "goals_against": 0, "points": 0}
            c = computed[team]
            c["played"]        += 1
            c["goals_for"]     += gf
            c["goals_against"] += ga
            c["goal_diff"]      = c["goals_for"] - c["goals_against"]
            if gf > ga:
                c["won"] += 1; c["points"] += 3
            elif gf == ga:
                c["drawn"] += 1; c["points"] += 1
            else:
                c["lost"] += 1

    for team, c in computed.items():
        grp = team_group.get(team, team_stats.get(team, {}).get("group", "Group Stage"))
        if team in team_stats:
            team_stats[team].update(c)
        else:
            team_stats[team] = {**c, "group": grp, "next_fixture": "No upcoming fixture"}
    print(f"  ✅ Goal/result stats computed for {len(computed)} teams from match results.")

    # ── Cards — always compute from bookings in each finished match ──────────
    yellow = {}
    red    = {}
    for m in finished:
        for booking in m.get("bookings", []):
            team = normalise((booking.get("team") or {}).get("name"))
            if not team:
                continue
            card = booking.get("card", "").upper()
            if "YELLOW" in card:
                yellow[team] = yellow.get(team, 0) + 1
            elif "RED" in card:
                red[team] = red.get(team, 0) + 1

    # Store per-team card counts in team_stats
    for team in team_stats:
        team_stats[team]["yellow_cards"] = yellow.get(team, 0)
        team_stats[team]["red_cards"]    = red.get(team, 0)
    # Also handle any teams only in match data
    for team in set(list(yellow.keys()) + list(red.keys())):
        if team not in team_stats:
            team_stats[team] = {"yellow_cards": yellow.get(team, 0),
                                "red_cards":    red.get(team, 0)}

    total_cards = sum(yellow.values()) + sum(red.values())
    print(f"  ✅ Cards: {sum(yellow.values())} yellow, {sum(red.values())} red across {len(yellow)+len(red)} teams.")
    if total_cards == 0:
        print("  ℹ️  No bookings in match data (may not be available on free tier).")

    return team_stats


# ─── Fetch next fixture per team ─────────────────────────────────────────────
def fetch_next_fixtures(headers, team_stats):
    """Add next_fixture string to each team in team_stats dict.
    Also patches goals/results from FINISHED matches when standings are stale."""
    url = "https://api.football-data.org/v4/competitions/WC/matches"
    try:
        r = SESSION.get(url, headers=headers,
                         params={"season": "2026"}, timeout=15)
        r.raise_for_status()
        all_matches = r.json().get("matches", [])

        # Patch team stats from match results if standings are lagging
        team_stats = compute_stats_from_matches(all_matches, team_stats)

        # Debug: show all unique statuses returned
        statuses = {}
        for m in all_matches:
            s = m.get("status", "UNKNOWN")
            statuses[s] = statuses.get(s, 0) + 1
        print(f"  Matches returned: {len(all_matches)} total. Statuses: {statuses}")

        # Debug: show first 3 match samples
        for m in all_matches[:3]:
            home = m.get("homeTeam", {}).get("name", "?")
            away = m.get("awayTeam", {}).get("name", "?")
            print(f"    Sample: {m.get('status')} | {home} vs {away} | {m.get('utcDate','')[:10]}")

        # Keep only upcoming matches
        upcoming_statuses = {"SCHEDULED", "TIMED", "POSTPONED"}
        scheduled = [m for m in all_matches if m.get("status") in upcoming_statuses]
        print(f"  Upcoming fixtures found: {len(scheduled)}")

        # Sort by date so first match found is soonest
        scheduled.sort(key=lambda m: m.get("utcDate", ""))

        # Build lookup: team_name → next match string
        next_fix = {}
        for m in scheduled:
            home = normalise(m.get("homeTeam", {}).get("name"))
            away = normalise(m.get("awayTeam", {}).get("name"))
            if not home or not away:
                continue
            utc_date = m.get("utcDate", "")
            # Convert UTC to AEST (UTC+10) using proper datetime arithmetic
            fixture_str = f"{home} vs {away}"
            if len(utc_date) >= 16:
                try:
                    dt_utc  = datetime.strptime(utc_date[:16], "%Y-%m-%dT%H:%M")
                    dt_aest = dt_utc + timedelta(hours=10)
                    fixture_str += f" · {dt_aest.strftime('%Y-%m-%d')} {dt_aest.strftime('%H:%M')} AEST"
                except Exception:
                    fixture_str += f" · {utc_date[:10]}"
            else:
                fixture_str += f" · {utc_date[:10]}"
            for team in (home, away):
                if team not in next_fix:  # only store first (soonest) fixture
                    next_fix[team] = fixture_str

        for team in team_stats:
            team_stats[team]["next_fixture"] = next_fix.get(team, "No upcoming fixture")

        print(f"  ✅ Next fixtures mapped for {len(next_fix)} teams.")

        team_stats = compute_advancement(all_matches, team_stats)

        # Fix next_fixture for 3rd-place contenders: the API fixture uses
        # placeholder names so they get no match string above. Find the
        # THIRD_PLACE fixture's date and wire it up explicitly.
        contenders = [t for t, s in team_stats.items()
                      if isinstance(s, dict) and s.get("advanced_to") == "THIRD_PLACE_CONTENDER"]
        if len(contenders) == 2:
            third_fix = next(
                (m for m in all_matches
                 if norm_stage(m.get("stage", "")) == "THIRD_PLACE"
                 and m.get("status") in ("TIMED", "SCHEDULED")),
                None
            )
            if third_fix:
                utc_date = third_fix.get("utcDate", "")
                fix_str = f"{contenders[0]} vs {contenders[1]}"
                if len(utc_date) >= 16:
                    try:
                        dt_utc  = datetime.strptime(utc_date[:16], "%Y-%m-%dT%H:%M")
                        dt_aest = dt_utc + timedelta(hours=10)
                        fix_str += f" · {dt_aest.strftime('%Y-%m-%d')} {dt_aest.strftime('%H:%M')} AEST"
                    except Exception:
                        fix_str += f" · {utc_date[:10]}"
                team_stats[contenders[0]]["next_fixture"] = fix_str
                team_stats[contenders[1]]["next_fixture"] = fix_str
                print(f"  ✅ 3rd-place fixture set for {contenders[0]} vs {contenders[1]}")

        recent = build_recent_results(all_matches)
        return team_stats, recent

    except Exception as e:
        print(f"[WARN] Fixtures fetch error: {e}", file=sys.stderr)
        for team, s in team_stats.items():
            if isinstance(s, dict):
                s.setdefault("next_fixture", "No upcoming fixture")

    return team_stats, []


# ─── Compute team advancement status ─────────────────────────────────────────
STAGE_ORDER = [
    "GROUP_STAGE", "ROUND_OF_32", "ROUND_OF_16",
    "QUARTER_FINALS", "SEMI_FINALS", "THIRD_PLACE", "FINAL",
]

# football-data.org uses LAST_32 / LAST_16 for the 2026 expanded rounds.
API_STAGE_MAP = {
    "GROUP_STAGE":   "GROUP_STAGE",
    "LAST_32":       "ROUND_OF_32",
    "ROUND_OF_32":   "ROUND_OF_32",
    "LAST_16":       "ROUND_OF_16",
    "ROUND_OF_16":   "ROUND_OF_16",
    "QUARTER_FINALS":"QUARTER_FINALS",
    "SEMI_FINALS":   "SEMI_FINALS",
    "THIRD_PLACE":   "THIRD_PLACE",
    "FINAL":         "FINAL",
}

def norm_stage(raw):
    return API_STAGE_MAP.get(raw.upper().strip() if raw else "", None)

def compute_advancement(all_matches, team_stats):
    """
    Sets advanced_to on each team in team_stats.
    During group stage: provisional top-2 per group → ROUND_OF_32, rest → None.
    During knockout stages: uses actual fixture appearances and match results.
    Also returns the current_stage string for the top-level data.json field.
    """
    # Determine current stage:
    # 1. Highest-order stage with a FINISHED or IN_PLAY match (authoritative)
    # 2. If still GROUP_STAGE but knockout TIMED fixtures exist, group stage is
    #    complete — use the highest knockout stage with TIMED matches instead.
    active_stages = set()
    timed_knockout_stages = set()
    knockout_stages_set = set(STAGE_ORDER) - {"GROUP_STAGE"}
    for m in all_matches:
        status = m.get("status", "")
        s = norm_stage(m.get("stage", ""))
        if not s:
            continue
        if status in ("FINISHED", "IN_PLAY"):
            active_stages.add(s)
        elif status in ("TIMED", "SCHEDULED") and s in knockout_stages_set:
            timed_knockout_stages.add(s)

    current_stage = "GROUP_STAGE"
    for s in reversed(STAGE_ORDER):
        if s in active_stages:
            current_stage = s
            break

    # Group stage is finished but no knockout match has kicked off yet —
    # promote to the first upcoming knockout stage so eliminations are shown.
    if current_stage == "GROUP_STAGE" and timed_knockout_stages:
        for s in STAGE_ORDER[1:]:
            if s in timed_knockout_stages:
                current_stage = s
                break

    print(f"  Tournament stage detected: {current_stage}")

    # Reset advanced_to for all teams
    for team in team_stats:
        team_stats[team]["advanced_to"] = None
        team_stats[team]["via_third"] = False

    if current_stage == "GROUP_STAGE":
        # Provisional: top 2 per group advance
        groups = {}
        for team, s in team_stats.items():
            g = s.get("group", "Unassigned")
            if g == "Group Stage": g = "Unassigned"
            groups.setdefault(g, []).append(team)

        for g, teams in groups.items():
            sorted_teams = sorted(
                teams,
                key=lambda t: (
                    team_stats[t].get("points", 0),
                    team_stats[t].get("goal_diff", 0),
                    team_stats[t].get("goals_for", 0),
                ),
                reverse=True,
            )
            for i, team in enumerate(sorted_teams):
                if i < 2:
                    team_stats[team]["advanced_to"] = "ROUND_OF_32"
                # positions 2+ stay None

    else:
        # ── Knockout phase ──────────────────────────────────────────────────
        # Step 1 — baseline from group standings (API knockout fixtures use
        # placeholder names like "Winner Group A" until results exist).
        # 2026 format: top 2 of each group + 8 best 3rd-placed teams = 32.
        groups = {}
        for team, s in team_stats.items():
            g = s.get("group", "Unassigned")
            if g in ("Group Stage", "Unassigned"):
                continue
            groups.setdefault(g, []).append(team)

        def grank(t):
            s = team_stats[t]
            return (s.get("points", 0), s.get("goal_diff", 0), s.get("goals_for", 0))

        qualifiers = set()
        third_qualifiers = set()
        thirds = []
        for g, teams in groups.items():
            st = sorted(teams, key=grank, reverse=True)
            for i, team in enumerate(st):
                if i < 2:
                    qualifiers.add(team)
                elif i == 2:
                    thirds.append(team)
        for team in sorted(thirds, key=grank, reverse=True)[:8]:
            third_qualifiers.add(team)

        all_qualifiers = qualifiers | third_qualifiers
        for team in team_stats:
            team_stats[team]["advanced_to"] = "ROUND_OF_32" if team in all_qualifiers else "eliminated"
            team_stats[team]["via_third"] = team in third_qualifiers

        # Step 2 — layer in real knockout results where the API has actual
        # team names (not placeholders). Resolve winner correctly:
        # fullTime → extraTime → penalties (knockout draws always resolve).
        NEXT_STAGE = {
            "ROUND_OF_32":   "ROUND_OF_16",
            "ROUND_OF_16":   "QUARTER_FINALS",
            "QUARTER_FINALS":"SEMI_FINALS",
            "SEMI_FINALS":   "FINAL",
            "FINAL":         "WINNER",
        }

        def knockout_winner(m):
            """Return (winner, loser) for a finished knockout match."""
            home = normalise(m.get("homeTeam", {}).get("name"))
            away = normalise(m.get("awayTeam", {}).get("name"))
            if not home or not away:
                return None, None
            score = m.get("score", {})
            for key in ("penalties", "extraTime", "fullTime"):
                s = score.get(key, {}) or {}
                h, a = s.get("home"), s.get("away")
                if h is not None and a is not None and h != a:
                    return (home, away) if h > a else (away, home)
            return None, None  # unresolved (match still in play)

        knockout_stages = set(STAGE_ORDER) - {"GROUP_STAGE"}
        for m in all_matches:
            if m.get("status") != "FINISHED":
                continue
            stage = norm_stage(m.get("stage", ""))
            if not stage or stage not in knockout_stages:
                continue
            winner, loser = knockout_winner(m)
            if stage == "THIRD_PLACE":
                # 3rd place match settled: winner=bronze, loser=4th
                if winner and winner in team_stats:
                    team_stats[winner]["advanced_to"] = "THIRD"
                if loser and loser in team_stats:
                    team_stats[loser]["advanced_to"] = "eliminated"
            elif stage == "SEMI_FINALS":
                # Semi-final losers play the 3rd place match — not eliminated yet
                if loser and loser in team_stats:
                    team_stats[loser]["advanced_to"] = "THIRD_PLACE_CONTENDER"
                if winner and winner in team_stats:
                    team_stats[winner]["advanced_to"] = "FINAL"
            else:
                if loser and loser in team_stats:
                    team_stats[loser]["advanced_to"] = "eliminated"
                if winner and winner in team_stats:
                    next_s = NEXT_STAGE.get(stage, stage)
                    team_stats[winner]["advanced_to"] = next_s  # WINNER if FINAL

    adv_count = sum(1 for s in team_stats.values() if s.get("advanced_to") not in (None, "eliminated"))
    elim_count = sum(1 for s in team_stats.values() if s.get("advanced_to") == "eliminated")
    print(f"  ✅ Advancement: {adv_count} advancing, {elim_count} eliminated, stage={current_stage}")

    # Store current_stage on a sentinel key so fetch_next_fixtures can return it
    team_stats["__tournament_stage__"] = current_stage
    return team_stats


# ─── Build recent results (today + yesterday in AEST) ────────────────────────
def build_recent_results(all_matches):
    """Return finished matches from today and yesterday in AEST (UTC+10).
    Labelled with their AEST date so the JS can show 'Today' vs 'Yesterday'."""
    from datetime import timezone as tz
    results = []
    now_aest   = datetime.now(tz.utc) + timedelta(hours=10)
    today_aest = now_aest.date()
    for m in all_matches:
        if m.get("status") != "FINISHED":
            continue
        utc_date = m.get("utcDate", "")
        try:
            match_dt_utc  = datetime.strptime(utc_date[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=tz.utc)
            match_dt_aest = match_dt_utc + timedelta(hours=10)
            match_date    = match_dt_aest.date()
        except Exception:
            continue
        days_ago = (today_aest - match_date).days
        if days_ago > 1:   # only today and yesterday
            continue
        home  = normalise(m.get("homeTeam", {}).get("name"))
        away  = normalise(m.get("awayTeam", {}).get("name"))
        score = m.get("score", {}).get("fullTime", {})
        hg    = score.get("home") or 0
        ag    = score.get("away") or 0
        if not home or not away:
            continue
        winner = home if hg > ag else (away if ag > hg else None)
        results.append({
            "home": home, "away": away,
            "home_goals": hg, "away_goals": ag,
            "aest_date": match_date.isoformat(),
            "days_ago": days_ago,
            "winner": winner,
            "date": utc_date[:10],
        })
    results.sort(key=lambda x: (x["days_ago"], x["aest_date"]))
    print(f"  ✅ Recent results (today/yesterday AEST): {len(results)} matches.")
    return results


# ─── Fetch top scorers ────────────────────────────────────────────────────────
def fetch_top_scorers(headers, limit=5):
    url = "https://api.football-data.org/v4/competitions/WC/scorers"
    try:
        r = SESSION.get(url, headers=headers,
                         params={"season": "2026", "limit": limit}, timeout=15)
        r.raise_for_status()
        scorers = r.json().get("scorers", [])
        result = []
        for s in scorers:
            result.append({
                "name":   s["player"]["name"],
                "team":   normalise(s["team"]["name"]),
                "goals":  s.get("numberOfGoals", s.get("goals", 0)),  # API uses both names
                "assists":s.get("assists", 0),
            })
        print(f"  ✅ Top {len(result)} scorers fetched.")
        return result
    except Exception as e:
        print(f"[WARN] Scorers fetch error: {e}", file=sys.stderr)
        return []


# ─── Fetch team discipline (yellow/red cards) from finished matches ───────────
def fetch_team_discipline(headers):
    """Try to aggregate yellow & red cards per team from finished match bookings."""
    url = "https://api.football-data.org/v4/competitions/WC/matches"
    try:
        r = SESSION.get(url, headers=headers,
                        params={"season": "2026", "status": "FINISHED"}, timeout=15)
        r.raise_for_status()
        matches = r.json().get("matches", [])
        if not matches:
            print("  No finished matches yet for discipline stats.")
            return {}

        yellow = {}
        red    = {}
        for m in matches:
            for booking in m.get("bookings", []):
                team = normalise((booking.get("team") or {}).get("name"))
                if not team:
                    continue
                card = booking.get("card", "")
                if "YELLOW" in card.upper():
                    yellow[team] = yellow.get(team, 0) + 1
                elif "RED" in card.upper():
                    red[team] = red.get(team, 0) + 1

        result = {}
        if yellow:
            top_y = max(yellow, key=yellow.get)
            result["most_yellow_team"] = {"team": top_y, "count": yellow[top_y]}
        if red:
            top_r = max(red, key=red.get)
            result["most_red_team"]    = {"team": top_r, "count": red[top_r]}

        print(f"  ✅ Discipline: yellow cards for {len(yellow)} teams, red for {len(red)} teams.")
        return result
    except Exception as e:
        print(f"[WARN] Discipline fetch error: {e}", file=sys.stderr)
        return {}


# ─── Derive tournament highlights from team stats ────────────────────────────
def compute_highlights(team_stats, top_scorers, discipline):
    highlights = {}

    if team_stats:
        by_gf = sorted(team_stats.items(), key=lambda x: x[1].get("goals_for", 0),    reverse=True)
        by_ga = sorted(team_stats.items(), key=lambda x: x[1].get("goals_against", 0), reverse=True)

        max_gf = by_gf[0][1].get("goals_for", 0) if by_gf else 0
        if max_gf > 0:
            highlights["top_scoring_team"] = {
                "goals": max_gf,
                "teams": [t for t, v in by_gf if v.get("goals_for", 0) == max_gf],
            }

        max_ga = by_ga[0][1].get("goals_against", 0) if by_ga else 0
        if max_ga > 0:
            highlights["most_conceded_team"] = {
                "goals": max_ga,
                "teams": [t for t, v in by_ga if v.get("goals_against", 0) == max_ga],
            }

    if top_scorers:
        highlights["top_scorers"] = top_scorers
        # Leading assists — pick player with most assists (ignoring 0s)
        top_assist = max(top_scorers, key=lambda s: s.get("assists") or 0, default=None)
        if top_assist and (top_assist.get("assists") or 0) > 0:
            highlights["top_assister"] = {
                "name":    top_assist["name"],
                "team":    top_assist["team"],
                "assists": top_assist["assists"],
            }

    # Cards — derive from per-team yellow_cards/red_cards stored in team_stats
    if team_stats:
        by_yellow = [(t, v.get("yellow_cards", 0)) for t, v in team_stats.items() if v.get("yellow_cards", 0) > 0]
        by_red    = [(t, v.get("red_cards",    0)) for t, v in team_stats.items() if v.get("red_cards",    0) > 0]
        if by_yellow:
            top_y = max(by_yellow, key=lambda x: x[1])
            highlights["most_yellow_team"] = {"team": top_y[0], "count": top_y[1]}
        if by_red:
            top_r = max(by_red, key=lambda x: x[1])
            highlights["most_red_team"] = {"team": top_r[0], "count": top_r[1]}

    # Fallback: use discipline dict if cards weren't in match bookings
    if "most_yellow_team" not in highlights and discipline.get("most_yellow_team"):
        highlights["most_yellow_team"] = discipline["most_yellow_team"]
    if "most_red_team" not in highlights and discipline.get("most_red_team"):
        highlights["most_red_team"] = discipline["most_red_team"]

    return highlights


# ─── Compute player standings ─────────────────────────────────────────────────
CANNOT_WIN = {"eliminated", "THIRD_PLACE_CONTENDER", "THIRD"}

def compute_players(team_probs, team_stats=None):
    players = []
    for p in DRAW:
        prob = 0.0
        for t in p["teams"]:
            if team_stats and team_stats.get(t, {}).get("advanced_to") in CANNOT_WIN:
                continue
            prob += team_probs.get(t, FALLBACK_PROBS.get(t, 0.05))
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
        time.sleep(2)
    else:
        print("\n⚠️  FOOTBALL_DATA_KEY not set — skipping match/stats fetch.")

    # ── Team stats, fixtures, scorers ─────────────────────────────────────────
    team_stats     = {}
    highlights     = {}
    discipline     = {}
    recent_results = []
    if fd_key:
        # Load previous data.json to preserve stats during knockout rounds
        out_path = os.path.join(os.path.dirname(__file__), "..", "data.json")
        prev_stats = {}
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                prev_stats = json.load(f).get("team_stats", {})
        except Exception:
            pass

        print("\nFetching group standings…")
        team_stats = fetch_team_stats(fd_headers, prev_stats)
        time.sleep(2)   # avoid hammering football-data.org free tier

        if team_stats:
            print("Fetching next fixtures…")
            team_stats, recent_results = fetch_next_fixtures(fd_headers, team_stats)
            tournament_stage = team_stats.pop("__tournament_stage__", "GROUP_STAGE")
            time.sleep(2)

            print("Fetching top scorers…")
            top_scorers = fetch_top_scorers(fd_headers)
            time.sleep(2)

            # Cards are already computed inside fetch_next_fixtures → compute_stats_from_matches
            # fetch_team_discipline is a fallback only if bookings weren't in match data
            discipline = {}
            if not any(v.get("yellow_cards", 0) > 0 for v in team_stats.values()):
                print("Fetching discipline (yellow/red cards) — bookings not in match data…")
                discipline = fetch_team_discipline(fd_headers)
                time.sleep(2)
            else:
                print("  ✅ Cards already computed from match bookings — skipping extra discipline fetch.")

            highlights  = compute_highlights(team_stats, top_scorers, discipline)

    # ── Build output ──────────────────────────────────────────────────────────
    players = compute_players(team_probs, team_stats)
    output = {
        "last_updated":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_match":       last_match,
        "source":           source,
        "tournament_stage": tournament_stage,
        "players":          players,
        "team_stats":       team_stats,
        "highlights":       highlights,
        "recent_results":   recent_results,
    }

    out_path = os.path.join(os.path.dirname(__file__), "..", "data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅  data.json written — {len(players)} players, {len(team_stats)} team stats, highlights: {list(highlights.keys())}")


if __name__ == "__main__":
    main()
