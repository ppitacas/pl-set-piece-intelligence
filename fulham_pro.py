import xml.etree.ElementTree as ET
import pandas as pd
from tactics import classify_corner_swing, classify_box_zone


def get_league_benchmarks(con, sp_type):
    kicks = con.execute("""
        SELECT set_piece_id, match_id, team, pass_type
        FROM set_piece_events
        WHERE phase = 'kick' AND pass_type IN (SELECT UNNEST(?))
    """, (list(sp_type),)).fetchdf()
    if kicks.empty:
        return pd.DataFrame()

    evs = con.execute("""
        SELECT set_piece_id, team, contact_number, type, shot_statsbomb_xg
        FROM set_piece_events
        WHERE phase = 'aftermath'
    """).fetchdf()

    c1 = evs[evs["contact_number"] == 1].drop_duplicates("set_piece_id")[["set_piece_id", "team"]].rename(columns={"team": "c1_team"})
    shots = evs[evs["type"] == "Shot"]
    att_shots = shots.merge(kicks[["set_piece_id", "team"]], on="set_piece_id", suffixes=("", "_kick"))
    att_xg = att_shots[att_shots["team"] == att_shots["team_kick"]].groupby("set_piece_id")["shot_statsbomb_xg"].sum().reset_index(name="att_xg")

    m = kicks.merge(c1, on="set_piece_id", how="left").merge(att_xg, on="set_piece_id", how="left")
    m["att_xg"] = m["att_xg"].fillna(0.0)
    m["is_c1"] = (m["c1_team"] == m["team"]).astype(int)
    m["is_lt"] = (m["pass_type"] == "Long Throw").astype(int)

    agg = m.groupby("team").agg(
        Set_Pieces=("set_piece_id", "count"),
        First_Contact_Win_Pct=("is_c1", lambda s: round(s.mean() * 100, 1)),
        Total_xG_For=("att_xg", lambda s: round(s.sum(), 2)),
        Long_Throws=("is_lt", "sum"),
    ).reset_index()
    agg["xG_per_10_SP"] = (agg["Total_xG_For"] / agg["Set_Pieces"] * 10).round(2)
    return agg.sort_values("xG_per_10_SP", ascending=False).reset_index(drop=True)


def get_gk_vulnerability(faced_kicks, faced_seq, team_name):
    if faced_kicks.empty or faced_seq.empty:
        return {}

    fk, fs = faced_kicks.copy(), faced_seq.copy()
    fk["Box_Zone"] = fk.apply(classify_box_zone, axis=1)
    six_yd_ids = set(fk[fk["Box_Zone"].str.contains("6-Yd", na=False)]["set_piece_id"])

    gk_evs = fs[(fs["team"] == team_name) & (fs["type"] == "Goal Keeper")]
    gk_claims = gk_evs[gk_evs["outcome"].isin(("Claimed", "Collected", "Saved", "Clear", "Punched"))]
    gk_player = gk_evs["player"].value_counts().index if not gk_evs.empty else "GK Unit"

    conceded_shots = fs[(fs["team"] != team_name) & (fs["type"] == "Shot")]
    six_yd_shots = conceded_shots[conceded_shots["location_x"] >= 114]
    six_yd_xg = float(six_yd_shots["shot_statsbomb_xg"].sum()) if not six_yd_shots.empty else 0.0

    return {
        "gk_name": gk_player,
        "six_yd_deliveries": len(six_yd_ids),
        "gk_claim_rate_pct": round(len(gk_claims) / max(1, len(six_yd_ids)) * 100, 1),
        "six_yd_shots_conceded": len(six_yd_shots),
        "six_yd_xg_conceded": round(six_yd_xg, 2),
    }


def to_sportscode_xml(clip_df, team_name):
    root = ET.Element("file")
    all_inst = ET.SubElement(root, "ALL_INSTANCES")

    for idx, row in enumerate(clip_df.itertuples(), 1):
        ts_str = str(getattr(row, "timestamp", "00:00:00"))
        parts = ts_str.split(":")
        base_sec = int(parts) * 3600 + int(parts) * 60 + float(parts) if len(parts) == 3 else 0.0
        period_offset = (int(getattr(row, "period", 1)) - 1) * 2700.0
        start_sec = max(0.0, base_sec + period_offset - 8.0)
        end_sec = base_sec + period_offset + 12.0

        inst = ET.SubElement(all_inst, "instance")
        ET.SubElement(inst, "ID").text = str(idx)
        ET.SubElement(inst, "start").text = f"{start_sec:.2f}"
        ET.SubElement(inst, "end").text = f"{end_sec:.2f}"
        ET.SubElement(inst, "code").text = f"{team_name} - {getattr(row, 'pass_type', 'Set Piece')}"

        for grp, attr in (("Taker", "player"), ("Delivery", "Swing"), ("Box Zone", "Box_Zone"), ("Outcome", "Result"), ("Fixture", "Fixture")):
            val = getattr(row, attr, None)
            if pd.notna(val):
                lbl = ET.SubElement(inst, "label")
                ET.SubElement(lbl, "group").text = grp
                ET.SubElement(lbl, "text").text = str(val)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_post_match_summary(own_team, own_kicks, own_seq, faced_kicks, faced_seq):
    att_k = len(own_kicks)
    def_k = len(faced_kicks)

    att_c1_pct = 0.0
    if not own_kicks.empty and not own_seq.empty:
        c1 = own_seq[own_seq["contact_number"] == 1].drop_duplicates("set_piece_id")
        att_c1_pct = round((c1["team"] == own_team).sum() / max(1, att_k) * 100, 1)

    def_c1_pct = 0.0
    if not faced_kicks.empty and not faced_seq.empty:
        dc1 = faced_seq[faced_seq["contact_number"] == 1].drop_duplicates("set_piece_id")
        def_c1_pct = round((dc1["team"] == own_team).sum() / max(1, def_k) * 100, 1)

    att_shots = own_seq[(own_seq["team"] == own_team) & (own_seq["type"] == "Shot")] if not own_seq.empty else pd.DataFrame()
    att_xg = round(float(att_shots["shot_statsbomb_xg"].sum()), 2) if not att_shots.empty else 0.0
    att_goals = int((att_shots["outcome"] == "Goal").sum()) if not att_shots.empty else 0

    def_shots = faced_seq[(faced_seq["team"] != own_team) & (faced_seq["type"] == "Shot")] if not faced_seq.empty else pd.DataFrame()
    def_xg = round(float(def_shots["shot_statsbomb_xg"].sum()), 2) if not def_shots.empty else 0.0
    def_goals = int((def_shots["outcome"] == "Goal").sum()) if not def_shots.empty else 0

    return {
        "att_k": att_k,
        "att_c1_pct": att_c1_pct,
        "att_shots": len(att_shots),
        "att_xg": att_xg,
        "att_goals": att_goals,
        "def_k": def_k,
        "def_c1_pct": def_c1_pct,
        "def_shots": len(def_shots),
        "def_xg": def_xg,
        "def_goals": def_goals,
    }

build_post_match_audit = build_post_match_summary

build_post_match_audit = build_post_match_summary


def build_post_match_audit(own_team, own_kicks, own_seq, faced_kicks, faced_seq):
    res = build_post_match_summary(own_team, own_kicks, own_seq, faced_kicks, faced_seq)
    res["att_g"] = res["att_goals"]
    res["def_g"] = res["def_goals"]
    return res






def detect_routines_and_flicks(kicks_df, seq_df, team_name):
    if kicks_df.empty or seq_df.empty:
        return pd.DataFrame(), {}

    rows = []
    for k in kicks_df.itertuples():
        sp_id = k.set_piece_id
        sub = seq_df[seq_df["set_piece_id"] == sp_id].sort_index()
        after = sub[sub["phase"] == "aftermath"]
        c1 = after[after["contact_number"] == 1]
        c2 = after[after["contact_number"] == 2]
        shots = after[(after["team"] == team_name) & (after["type"] == "Shot")]

        if c1.empty:
            continue

        r1 = next(c1.itertuples())
        r2 = next(c2.itertuples()) if not c2.empty else None
        c1_team = getattr(r1, "team", "")
        c1_x = float(r1.location_x) if pd.notna(getattr(r1, "location_x", None)) else 0.0
        c1_y = float(r1.location_y) if pd.notna(getattr(r1, "location_y", None)) else 40.0
        kick_x = float(k.location_x) if pd.notna(getattr(k, "location_x", None)) else 120.0
        kick_y = float(k.location_y) if pd.notna(getattr(k, "location_y", None)) else 40.0
        end_x = float(k.end_x) if pd.notna(getattr(k, "end_x", None)) else c1_x
        end_y = float(k.end_y) if pd.notna(getattr(k, "end_y", None)) else c1_y

        kick_dist = ((end_x - kick_x) ** 2 + (end_y - kick_y) ** 2) ** 0.5
        is_near_post = (c1_x >= 108.0) and ((kick_y < 40.0 and c1_y <= 36.5) or (kick_y >= 40.0 and c1_y >= 43.5))
        is_far_post = (c1_x >= 108.0) and ((kick_y < 40.0 and c1_y >= 44.5) or (kick_y >= 40.0 and c1_y <= 35.5))
        is_edge_box = (96.0 <= c1_x <= 107.0) and (24.0 <= c1_y <= 56.0)
        is_six_yard_pin = (c1_x >= 114.0) and (33.0 <= c1_y <= 47.0)
        has_c2_att = (r2 is not None) and (getattr(r2, "team", "") == team_name)
        xg = round(float(shots["shot_statsbomb_xg"].sum()), 3) if not shots.empty else 0.0
        is_goal = bool(shots["outcome"].astype(str).str.strip().eq("Goal").any()) if (not shots.empty and "outcome" in shots.columns) else False

        routine_tag = "Standard Central Delivery"
        if str(getattr(k, "pass_type", "")) == "Corner" and kick_dist < 16.5:
            routine_tag = "Short Corner Overload / Angle Shift"
        elif c1_team == team_name and is_edge_box:
            routine_tag = "Edge-of-Box D-Arc Cutback"
        elif c1_team == team_name and is_near_post and (has_c2_att or xg > 0):
            routine_tag = "Near-Post Flick-On Routine"
        elif c1_team == team_name and is_far_post:
            routine_tag = "Far-Post Isolation / Back-Post Knockdown"
        elif c1_team == team_name and is_six_yard_pin:
            routine_tag = "6-Yard Keeper-Pin & Block"
        elif c1_team == team_name and has_c2_att and xg >= 0.06:
            routine_tag = "Off-Ball Screen / Lay-Off Routine"

        p1_name = getattr(r1, "player", "") or ""
        p2_name = (getattr(r2, "player", "-") or "-") if r2 is not None else "-"
        rows.append({
            "set_piece_id": sp_id,
            "match_id": k.match_id,
            "timestamp": getattr(k, "timestamp", ""),
            "pass_type": getattr(k, "pass_type", ""),
            "Taker": getattr(k, "player", ""),
            "1st_Contact": p1_name if c1_team == team_name else f"Cleared ({p1_name})",
            "2nd_Contact": p2_name,
            "Routine_Pattern": routine_tag,
            "c1_x": c1_x,
            "c1_y": c1_y,
            "c2_x": float(r2.location_x) if (r2 is not None and pd.notna(getattr(r2, "location_x", None))) else None,
            "c2_y": float(r2.location_y) if (r2 is not None and pd.notna(getattr(r2, "location_y", None))) else None,
            "xG": xg,
            "Goal": "GOAL" if is_goal else ("Shot" if xg > 0 else "-"),
        })

    res_df = pd.DataFrame(rows)
    if res_df.empty:
        return res_df, {}

    summary = {
        "total_analyzed": len(res_df),
        "near_post_flicks": int((res_df["Routine_Pattern"] == "Near-Post Flick-On Routine").sum()),
        "screen_routines": int(res_df["Routine_Pattern"].isin(("Off-Ball Screen / Lay-Off Routine", "6-Yard Keeper-Pin & Block")).sum()),
        "flick_xg": round(float(res_df[res_df["Routine_Pattern"] == "Near-Post Flick-On Routine"]["xG"].sum()), 2),
        "screen_xg": round(float(res_df[res_df["Routine_Pattern"].isin(("Off-Ball Screen / Lay-Off Routine", "6-Yard Keeper-Pin & Block"))]["xG"].sum()), 2),
    }
    return res_df, summary
