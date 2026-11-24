import math


def classify_corner_swing(row):
    ptype = row.get("pass_type")
    if ptype == "Long Throw":
        return "Long Throw"
    if ptype != "Corner":
        return row.get("pass_technique") or "Direct / Cross"

    tech = str(row.get("pass_technique") or "")
    dx = (row.get("end_x") or 0) - (row.get("location_x") or 0)
    dy = (row.get("end_y") or 0) - (row.get("location_y") or 0)
    dist = math.hypot(dx, dy)

    if dist < 14.0:
        return "Short Corner"
    if "Inswinging" in tech:
        return "Inswinger"
    if "Outswinging" in tech:
        return "Outswinger"
    if "Straight" in tech:
        return "Driven / Straight"
    return "Other / Unclassified"


def classify_box_zone(row):
    ex, ey = row.get("end_x"), row.get("end_y")
    lx, ly = row.get("location_x"), row.get("location_y")
    if ex is None or ey is None:
        return "Unknown"

    dist = math.hypot((ex - (lx or 120)), (ey - (ly or 40)))
    if row.get("pass_type") == "Corner" and dist < 14.0:
        return "Short Routine"

    from_left = (ly or 40) < 40
    if ex < 102:
        return "Edge of Box / Deep"
    if ey < 30 or ey > 50:
        return "Wide Box"

    if ex >= 114:
        if (from_left and ey < 37) or (not from_left and ey > 43):
            return "Near Post (6-Yd)"
        elif (from_left and ey > 43) or (not from_left and ey < 37):
            return "Far Post (6-Yd)"
        return "Central 6-Yard"
    else:
        if (from_left and ey < 36) or (not from_left and ey > 44):
            return "Near Post Zone"
        elif (from_left and ey > 44) or (not from_left and ey < 36):
            return "Far Post Zone"
        return "Penalty Spot / Central"


def summarize_opposition_defending(def_kicks_df):
    return def_kicks_df


def generate_matchup_brief(own_team, opp_team, own_kicks, own_seq, *args):
    if len(args) == 6:
        opp_kicks, opp_seq, opp_faced_kicks, opp_faced_seq, own_hops, opp_hops = args
    else:
        opp_faced_kicks, opp_faced_seq, own_hops, opp_hops = args
        opp_kicks, opp_seq = opp_faced_kicks, opp_faced_seq

    briefs = []
    if not own_kicks.empty and not opp_faced_kicks.empty:
        ok = own_kicks.copy()
        ok["Box_Zone"] = ok.apply(classify_box_zone, axis=1)
        best_own_z = ok["Box_Zone"].value_counts().index[0]

        fk = opp_faced_kicks.copy()
        fk["Box_Zone"] = fk.apply(classify_box_zone, axis=1)
        weak_opp_z = fk["Box_Zone"].value_counts().index[0]
        briefs.append(f"Attacking Target Zone: {own_team} attacks {best_own_z} most frequently; target {opp_team}'s high-volume {weak_opp_z}.")

    if not opp_kicks.empty:
        opp_k = opp_kicks.copy()
        opp_k["Swing"] = opp_k.apply(classify_corner_swing, axis=1)
        top_swing = opp_k["Swing"].value_counts().index[0]
        top_taker = opp_k["player"].value_counts().index[0]
        briefs.append(f"Opposition Primary Threat: {opp_team} favors {top_swing} deliveries via {top_taker}.")

    if not own_hops.empty and not opp_hops.empty:
        # Prefer traditional defensive shirt numbers (#2-#6, #12-#27) over #7-#11/#30 attackers when assigning markers
        def_mask = own_hops["#"].astype(str).isin(("2", "3", "4", "5", "6", "12", "14", "15", "16", "18", "21", "22", "23", "24", "25", "26", "27", "37"))
        marker_df = own_hops[def_mask] if def_mask.any() else own_hops
        own_top = marker_df["Player"].iloc[0]
        opp_top = opp_hops["Player"].iloc[0]
        briefs.append(f"Aerial Matchup Alert: Assign primary aerial defender ({own_top}) to track {opp_team}'s top box target ({opp_top}).")

    return briefs

import pandas as pd
import xml.etree.ElementTree as ET


def build_league_trends_table(con, sp_types):
    all_kicks = con.execute("""
        SELECT * FROM set_piece_events
        WHERE phase = 'Kick' OR phase = 'kick'
          AND pass_type IN (SELECT UNNEST(?))
    """, (list(sp_types),)).fetchdf()

    all_after = con.execute("""
        SELECT set_piece_id, team, type, contact_number, shot_statsbomb_xg, outcome
        FROM set_piece_events
        WHERE phase = 'aftermath'
    """).fetchdf()

    if all_kicks.empty:
        return pd.DataFrame()

    all_kicks["Swing"] = all_kicks.apply(classify_corner_swing, axis=1)
    c1 = all_after[all_after["contact_number"] == 1].groupby("set_piece_id").first().reset_index()[["set_piece_id", "team"]].rename(columns={"team": "c1_team"})
    xg_df = all_after[all_after["type"] == "Shot"].groupby(["set_piece_id", "team"])["shot_statsbomb_xg"].sum().reset_index()
    g_only = all_after[(all_after["type"] == "Shot") & (all_after["outcome"] == "Goal")].groupby(["set_piece_id", "team"]).size().reset_index(name="goals")

    merged = all_kicks.merge(c1, on="set_piece_id", how="left")
    merged["att_c1_win"] = (merged["c1_team"] == merged["team"]).astype(int)

    rows = []
    for team, grp in merged.groupby("team"):
        att_k = len(grp)
        att_c1_pct = round(grp["att_c1_win"].mean() * 100, 1)
        ins_pct = round((grp["Swing"] == "Inswinger").mean() * 100, 1)
        out_pct = round((grp["Swing"] == "Outswinger").mean() * 100, 1)
        lt_cnt = int((grp["Swing"] == "Long Throw").sum())

        team_sp_ids = set(grp["set_piece_id"])
        att_xg = float(xg_df[xg_df["set_piece_id"].isin(team_sp_ids) & (xg_df["team"] == team)]["shot_statsbomb_xg"].sum())
        att_g = int(g_only[g_only["set_piece_id"].isin(team_sp_ids) & (g_only["team"] == team)]["goals"].sum())

        faced = merged[merged["conceded_by"] == team] if "conceded_by" in merged.columns else pd.DataFrame()
        rows.append({
            "Team": team,
            "Set Pieces": att_k,
            "Att 1st Contact %": att_c1_pct,
            "Inswinger %": ins_pct,
            "Outswinger %": out_pct,
            "Long Throws": lt_cnt,
            "Att xG": round(att_xg, 2),
            "xG / 10 SP": round(att_xg / att_k * 10, 2) if att_k else 0.0,
            "Goals": att_g,
        })

    return pd.DataFrame(rows).sort_values("xG / 10 SP", ascending=False).reset_index(drop=True)


def generate_sportscode_xml(clip_df, team_name, pre_roll=5.0, post_roll=15.0):
    root = ET.Element("file")
    all_inst = ET.SubElement(root, "ALL_INSTANCES")

    def _to_sec(ts):
        try:
            h, m, s = str(ts).split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception:
            return 0.0

    for idx, (_, row) in enumerate(clip_df.iterrows(), 1):
        inst = ET.SubElement(all_inst, "instance")
        ET.SubElement(inst, "ID").text = str(idx)
        t0 = _to_sec(row.get("timestamp", "00:00:00"))
        half_offset = 2700.0 if int(row.get("period", 1)) == 2 else 0.0
        start = max(0.0, half_offset + t0 - pre_roll)
        end = half_offset + t0 + post_roll
        ET.SubElement(inst, "start").text = f"{start:2f}"
        ET.SubElement(inst, "end").text = f"{end:.2f}"
        ET.SubElement(inst, "code").text = f"{team_name} - {row.get('pass_type', 'Set Piece')}"
        for grp, val in (("Taker", row.get("player")), ("Delivery", row.get("Swing")), ("Zone", row.get("Box_Zone")), ("Outcome", row.get("Result"))):
            if val:
                lbl = ET.SubElement(inst, "label")
                ET.SubElement(lbl, "group").text = grp
                ET.SubElement(lbl, "text").text = str(val)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
