import os
import math
import warnings
warnings.filterwarnings("ignore")
import duckdb
import pandas as pd
from statsbombpy import sb

DB_PATH = "data/pl_setpieces.duckdb"
COMPETITION_ID = 2
SEASON_ID = 27


def init_db(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            match_id INTEGER PRIMARY KEY,
            match_date DATE,
            home_team VARCHAR,
            away_team VARCHAR,
            home_score INTEGER,
            away_score INTEGER
        );
        CREATE TABLE IF NOT EXISTS player_hops (
            match_id INTEGER,
            match_date DATE,
            team_name VARCHAR,
            player_id INTEGER,
            player_name VARCHAR,
            jersey_number INTEGER,
            hops_rating DOUBLE,
            PRIMARY KEY (match_id, player_id)
        );
        CREATE TABLE IF NOT EXISTS set_piece_events (
            set_piece_id VARCHAR,
            match_id INTEGER,
            phase VARCHAR,
            contact_number INTEGER,
            event_id VARCHAR,
            index INTEGER,
            period INTEGER,
            timestamp VARCHAR,
            seconds_from_kick DOUBLE,
            possession INTEGER,
            possession_team VARCHAR,
            team VARCHAR,
            player VARCHAR,
            player_id INTEGER,
            type VARCHAR,
            pass_type VARCHAR,
            pass_technique VARCHAR,
            location_x DOUBLE,
            location_y DOUBLE,
            end_x DOUBLE,
            end_y DOUBLE,
            shot_statsbomb_xg DOUBLE,
            outcome VARCHAR,
            PRIMARY KEY (set_piece_id, event_id)
        );
        CREATE TABLE IF NOT EXISTS frames_360 (
            event_id VARCHAR PRIMARY KEY,
            match_id INTEGER,
            visible_area VARCHAR,
            freeze_frame VARCHAR
        );
    """)


def to_seconds(ts_str):
    h, m, s = ts_str.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def unpack_xy(val):
    if isinstance(val, list) and len(val) >= 2:
        x, y = val
        return float(x), float(y)
    return None, None


def is_long_throw(row):
    if row.get("pass_type") != "Throw-in":
        return False
    lx, ly = unpack_xy(row.get("location"))
    ex, ey = unpack_xy(row.get("pass_end_location"))
    if lx is None or ex is None:
        return False
    dist = math.hypot(ex - lx, ey - ly)
    return lx >= 75 and ex >= 96 and dist >= 22.0


def extract_lineups_and_aerial(con, match_id, match_date, events):
    lineups = sb.lineups(match_id=match_id)
    aerial_events = events[events["type"] == "Duel"]
    rows = []
    name_map = {}

    for team_name, df_team in lineups.items():
        for _, row in df_team.iterrows():
            pid = row["player_id"]
            raw_name = row.get("player_nickname") or row["player_name"]
            parts = str(raw_name).split()
            clean_name = f"{parts} {parts[-1]}" if len(parts) >= 3 else raw_name
            name_map[pid] = clean_name

            p_duels = aerial_events[aerial_events["player_id"] == pid]
            if len(p_duels) > 0:
                won = p_duels["duel_outcome"].isin(("Won", "Success", "Success In Play", "Success Out")).sum()
                hops = round((won + 1.5) / (len(p_duels) + 3.0), 3)
            else:
                hops = 0.500

            rows.append({
                "match_id": match_id,
                "match_date": match_date,
                "team_name": team_name,
                "player_id": pid,
                "player_name": clean_name,
                "jersey_number": row.get("jersey_number"),
                "hops_rating": hops,
            })

    if rows:
        df_hops = pd.DataFrame(rows)
        con.execute("INSERT OR REPLACE INTO player_hops SELECT * FROM df_hops")
    return name_map


def process_match(con, match_id, match_date):
    events = sb.events(match_id=match_id).sort_values(["period", "index"]).reset_index(drop=True)
    events["sec"] = events["timestamp"].apply(to_seconds)
    name_map = extract_lineups_and_aerial(con, match_id, match_date, events)

    is_corner = events["pass_type"] == "Corner"
    is_att_fk = (events["pass_type"] == "Free Kick") & (
        events["location"].apply(lambda loc: (next(iter(unpack_xy(loc))) or 0) >= 60)
    )
    is_lt = events.apply(is_long_throw, axis=1)
    kicks = events[is_corner | is_att_fk | is_lt]

    touch_types = {"Pass", "Shot", "Clearance", "Ball Recovery", "Interception", "Duel", "Carry", "Dribble", "Block", "Goal Keeper"}
    all_rows = []

    for _, kick in kicks.iterrows():
        sp_id = f"{match_id}_{kick['id']}"
        k_poss = kick["possession"]
        k_period = kick["period"]
        k_sec = kick["sec"]

        buildup = events[(events["period"] == k_period) & (events["possession"] == k_poss - 1)]
        aftermath = events[
            (events["period"] == k_period) &
            (events["index"] > kick["index"]) &
            ((events["sec"] - k_sec <= 20.0) | (events["possession"].isin((k_poss, k_poss + 1))))
        ]
        seq = pd.concat([buildup, pd.DataFrame([kick]), aftermath]).drop_duplicates("id")

        contact_cnt = 0
        for _, ev in seq.iterrows():
            if ev["index"] < kick["index"]:
                phase, c_num = "buildup", None
            elif ev["id"] == kick["id"]:
                phase, c_num = "kick", 0
            else:
                phase = "aftermath"
                if ev["type"] in touch_types:
                    contact_cnt += 1
                    c_num = min(contact_cnt, 3)
                else:
                    c_num = None

            lx, ly = unpack_xy(ev.get("location"))
            raw_end = ev.get("pass_end_location") or ev.get("shot_end_location") or ev.get("carry_end_location")
            ex, ey = unpack_xy(raw_end)
            outcome = ev.get("pass_outcome") or ev.get("shot_outcome") or ev.get("duel_outcome") or ev.get("interception_outcome")
            pid = ev.get("player_id")
            clean_player = name_map.get(pid, ev.get("player"))
            p_type = "Long Throw" if ev["id"] == kick["id"] and ev.get("pass_type") == "Throw-in" else ev.get("pass_type")

            all_rows.append({
                "set_piece_id": sp_id,
                "match_id": match_id,
                "phase": phase,
                "contact_number": c_num,
                "event_id": ev["id"],
                "index": ev["index"],
                "period": ev["period"],
                "timestamp": ev["timestamp"],
                "seconds_from_kick": round(ev["sec"] - k_sec, 2),
                "possession": ev["possession"],
                "possession_team": ev.get("possession_team"),
                "team": ev["team"],
                "player": clean_player,
                "player_id": pid,
                "type": ev["type"],
                "pass_type": p_type,
                "pass_technique": ev.get("pass_technique"),
                "location_x": lx,
                "location_y": ly,
                "end_x": ex,
                "end_y": ey,
                "shot_statsbomb_xg": float(ev.get("shot_statsbomb_xg") or 0.0),
                "outcome": outcome,
            })

    if all_rows:
        df_sp = pd.DataFrame(all_rows)
        con.execute("INSERT OR REPLACE INTO set_piece_events SELECT * FROM df_sp")


def sync_all():
    os.makedirs("data", exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = duckdb.connect(DB_PATH)
    init_db(con)
    matches = sb.matches(competition_id=COMPETITION_ID, season_id=SEASON_ID).sort_values("match_date")
    print(f"Indexing {len(matches)} matches with Corners, Free Kicks & Long Throws...", flush=True)
    for i, (_, m) in enumerate(matches.iterrows(), 1):
        mid = int(m["match_id"])
        if i % 25 == 0 or i == 1:
            print(f"[{i}/{len(matches)}] Processing {m['home_team']} vs {m['away_team']}...", flush=True)
        process_match(con, mid, m["match_date"])
        con.execute("INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?)", [mid, m["match_date"], m["home_team"], m["away_team"], m["home_score"], m["away_score"]])
    con.close()
    print("Sync complete!", flush=True)


if __name__ == "__main__":
    sync_all()
