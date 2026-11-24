from visuals import plot_aerial_mismatch, plot_flick_and_screen_routines
import os
import duckdb
import pandas as pd
import streamlit as st
from tactics import classify_corner_swing, classify_box_zone, generate_matchup_brief
from visuals import (
    plot_delivery_and_contacts,
    plot_swing_deliveries,
    plot_delivery_zone_heatmap,
    plot_defensive_vulnerability,
    plot_routine_sequence,
)
from pdf_generator import build_matchday_pdf
from fulham_pro import get_league_benchmarks, get_gk_vulnerability, to_sportscode_xml, build_post_match_audit, detect_routines_and_flicks

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pl_setpieces.duckdb")
st.set_page_config(page_title="Premier League Set-Piece Lab", layout="wide")


@st.cache_resource
def get_con():
    return duckdb.connect(DB_PATH, read_only=True)


def get_team_slice(con, team_name, sp_type, side_filter, last_n):
    matches_df = con.execute("""
        SELECT match_id, match_date, home_team, away_team FROM matches
        WHERE home_team = ? OR away_team = ?
        ORDER BY match_date DESC
    """, (team_name, team_name)).fetchdf()

    if last_n > 0:
        matches_df = matches_df.head(last_n)
    m_ids = matches_df["match_id"].tolist()
    if not m_ids:
        return matches_df, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    kicks = con.execute("""
        SELECT * FROM set_piece_events
        WHERE team = ? AND phase = 'kick'
          AND pass_type IN (SELECT UNNEST(?))
          AND match_id IN (SELECT UNNEST(?))
    """, (team_name, list(sp_type), m_ids)).fetchdf()

    if side_filter == "Left (y < 40)":
        kicks = kicks[kicks["location_y"] < 40]
    elif side_filter == "Right (y >= 40)":
        kicks = kicks[kicks["location_y"] >= 40]

    sp_ids = kicks["set_piece_id"].tolist()
    seq = con.execute(
        "SELECT * FROM set_piece_events WHERE set_piece_id IN (SELECT UNNEST(?))", (sp_ids,)
    ).fetchdf() if sp_ids else pd.DataFrame()

    faced_kicks = con.execute("""
        SELECT * FROM set_piece_events
        WHERE phase = 'kick' AND pass_type IN (SELECT UNNEST(?))
          AND match_id IN (SELECT UNNEST(?)) AND team != ?
    """, (list(sp_type), m_ids, team_name)).fetchdf()

    f_ids = faced_kicks["set_piece_id"].tolist()
    faced_seq = con.execute(
        "SELECT * FROM set_piece_events WHERE set_piece_id IN (SELECT UNNEST(?))", (f_ids,)
    ).fetchdf() if f_ids else pd.DataFrame()

    return matches_df, kicks, seq, faced_kicks, faced_seq


def get_latest_team_hops(con, team_name):
    return con.execute("""
        WITH ranked AS (
            SELECT player_name, jersey_number, hops_rating, match_date,
                   ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY match_date DESC) AS rn
            FROM player_hops
            WHERE team_name = ? AND player_name IS NOT NULL
        )
        SELECT ROW_NUMBER() OVER (ORDER BY hops_rating DESC) AS "Rank",
               COALESCE(CAST(jersey_number AS VARCHAR), '-') AS "#",
               player_name AS "Player",
               ROUND(hops_rating, 3) AS "HOPS"
        FROM ranked WHERE rn = 1
        ORDER BY hops_rating DESC
        LIMIT 12
    """, (team_name,)).fetchdf()


def render_team_dashboard(team_name, kicks_df, seq_df, faced_kicks, faced_seq):
    att_k = len(kicks_df)
    att_s = seq_df[(seq_df["team"] == team_name) & (seq_df["type"] == "Shot")] if not seq_df.empty else pd.DataFrame()
    att_xg = float(att_s["shot_statsbomb_xg"].sum()) if not att_s.empty else 0.0
    att_g = int((att_s["outcome"] == "Goal").sum()) if not att_s.empty else 0

    def_k = len(faced_kicks)
    def_s = faced_seq[(faced_seq["team"] != team_name) & (faced_seq["type"] == "Shot")] if not faced_seq.empty else pd.DataFrame()
    def_xg = float(def_s["shot_statsbomb_xg"].sum()) if not def_s.empty else 0.0
    def_g = int((def_s["outcome"] == "Goal").sum()) if not def_s.empty else 0
    lt_cnt = int((kicks_df["pass_type"] == "Long Throw").sum()) if not kicks_df.empty else 0

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Attacking Set Pieces", att_k)
    m2.metric("Att xG (Goals)", f"{att_xg:.2f} ({att_g}G)", f"{(att_xg/att_k*10 if att_k else 0):.2f} / 10 SP")
    m3.metric("Set Pieces Faced", def_k)
    m4.metric("Def xG Conceded", f"{def_xg:.2f} ({def_g}G)", f"{(def_xg/def_k*10 if def_k else 0):.2f} / 10 SP", delta_color="inverse")
    m5.metric("Long Throws", lt_cnt)

    view_filter = st.radio(
        f"{team_name} Pitch Map Filter",
        ("All Deliveries & Contacts", "High-Threat Only (Shots & Goals)"),
        horizontal=True,
        key=f"vf_{team_name}_{att_k}_{def_k}",
    )
    plot_seq = seq_df
    if view_filter == "High-Threat Only (Shots & Goals)" and not seq_df.empty:
        shot_ids = set(seq_df[(seq_df["team"] == team_name) & (seq_df["type"] == "Shot")]["set_piece_id"])
        plot_seq = seq_df[seq_df["set_piece_id"].isin(shot_ids)]

    c1, c2 = st.columns(2)
    with c1:
        if not plot_seq.empty:
            st.pyplot(plot_delivery_and_contacts(plot_seq, title=f"{team_name} Attacking Deliveries & Contacts"))
    with c2:
        if not kicks_df.empty:
            st.pyplot(plot_swing_deliveries(kicks_df, title=f"{team_name} Delivery Types & Swing"))

    c3, c4 = st.columns(2)
    with c3:
        if not faced_kicks.empty:
            st.pyplot(plot_defensive_vulnerability(faced_kicks, faced_seq, team_name))
    with c4:
        if not kicks_df.empty:
            st.pyplot(plot_delivery_zone_heatmap(kicks_df, title=f"{team_name} Attacking Target Zones"))


def main():
    st.title("Premier League — Set-Piece Analysis & Aerial Engine")
    st.caption("First-Team Set-Piece Intelligence Suite | Event-Chain xG, 1st-Contact % Benchmarks, GK Box Vulnerability, Hudl Sportscode XML & Matchday PDFs")
    if not os.path.exists(DB_PATH):
        st.error("Database not found.")
        return

    con = get_con().cursor().cursor()
    teams = sorted(con.execute("SELECT DISTINCT home_team FROM matches").fetchdf()["home_team"].tolist())

    with st.sidebar:
        st.header("Matchup Filters")
        own_team = st.selectbox("Own Team", teams, index=0)
        opp_team = st.selectbox("Opposition Team", teams, index=min(1, len(teams) - 1))
        sp_type = st.multiselect("Set-Piece Type", ("Corner", "Free Kick", "Long Throw"), default=("Corner", "Free Kick", "Long Throw"))
        side_filter = st.radio("Delivery Side", ("All", "Left (y < 40)", "Right (y >= 40)"))
        review_mode = st.radio("Analysis Scope", ("Season / Form Window", "Single-Match Post-Match Review"))
        last_n = 0
        sel_match_id = None
        if review_mode == "Single-Match Post-Match Review":
            m_all = con.execute("SELECT match_id, match_date, home_team, away_team, home_score, away_score FROM matches WHERE home_team = ? OR away_team = ? ORDER BY match_date ASC", (own_team, own_team)).fetchdf()
            m_all["MW"] = range(1, len(m_all) + 1)
            m_all = m_all.sort_values("MW", ascending=False)
            m_all["lbl"] = "MW " + m_all["MW"].astype(str) + " (" + m_all["match_date"].astype(str) + ") | " + m_all["home_team"] + " " + m_all["home_score"].astype(str) + "-" + m_all["away_score"].astype(str) + " " + m_all["away_team"]
            picked = st.selectbox("Select Fixture for Post-Match Review", m_all["lbl"].tolist())
            sel_match_id = int(next(iter(m_all[m_all["lbl"] == picked]["match_id"])))
        else:
            last_n = st.slider("Form Window (Last N Matches, 0 = Full Season)", 0, 38, 0)

    opp_matches_df, kicks_df, seq_df, opp_faced_kicks, faced_seq_df = get_team_slice(con, opp_team, sp_type, side_filter, last_n)
    own_matches_df, own_kicks_df, own_seq_df, own_faced_kicks, own_faced_seq = get_team_slice(con, own_team, sp_type, side_filter, last_n)

    if sel_match_id is not None:
        own_matches_df = own_matches_df[own_matches_df["match_id"] == sel_match_id]
        own_kicks_df = own_kicks_df[own_kicks_df["match_id"] == sel_match_id]
        own_seq_df = own_seq_df[own_seq_df["match_id"] == sel_match_id]
        own_faced_kicks = own_faced_kicks[own_faced_kicks["match_id"] == sel_match_id]
        own_faced_seq = own_faced_seq[own_faced_seq["match_id"] == sel_match_id]

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        f"1. Opposition ({opp_team})",
        f"2. Our Team ({own_team})",
        "3. Takers & Box Receivers",
        "4. Video Clipping Playlist",
        "5. Aerial Matchup & PDF",
        "6. Matchup Edge & Goal Replay",
        "7. League-Wide Trends",
    ])

    with tab1:
        st.subheader(f"Opposition Scouting — {opp_team}")
        render_team_dashboard(opp_team, kicks_df, seq_df, opp_faced_kicks, faced_seq_df)

    with tab2:
        mode_label = picked if sel_match_id is not None else "Full Season / Form Window"
        st.subheader(f"Own Team Review — {own_team} ({mode_label})")
        if sel_match_id is not None:
            audit = build_post_match_audit(own_team, own_kicks_df, own_seq_df, own_faced_kicks, own_faced_seq)
            st.success(
                f"**Post-Match Set-Piece Audit ({picked}):**  \n"
                f"- **Attacking Execution:** {audit['att_k']} Set Pieces | 1st-Contact Win Rate: **{audit['att_c1_pct']}%** | Expected vs. Actual: **{audit['att_xg']} xG vs. {audit['att_g']} Goals**  \n"
                f"- **Defensive Execution:** {audit['def_k']} Set Pieces Faced | Defensive 1st-Contact Clear Rate: **{audit['def_c1_pct']}%** | Conceded: **{audit['def_xg']} xG vs. {audit['def_g']} Goals**"
            )
            if st.button("Generate Post-Match Review PDF"):
                os.makedirs("exports", exist_ok=True)
                pm_att = "exports/tmp_pm_att.png"
                pm_def = "exports/tmp_pm_def.png"
                pm_swg = "exports/tmp_pm_swg.png"
                pm_zon = "exports/tmp_pm_zon.png"
                plot_delivery_and_contacts(own_seq_df, show_contacts=(1, 3), title=f"{own_team} Post-Match Deliveries & Contacts", save_path=pm_att)
                plot_defensive_vulnerability(own_faced_kicks, own_faced_seq, own_team, save_path=pm_def)
                plot_swing_deliveries(own_kicks_df, title=f"{own_team} Delivery Swing Split", save_path=pm_swg)
                plot_delivery_zone_heatmap(own_kicks_df, title=f"{own_team} Target Zones", save_path=pm_zon)
                pm_takers = own_kicks_df.groupby("player").size().reset_index(name="Kicks").sort_values("Kicks", ascending=False).head(6) if not own_kicks_df.empty else pd.DataFrame(columns=["player", "Kicks"])
                pm_bullets = [
                    f"Post-Match Fixture: {picked}",
                    f"Attacking Set Pieces: {audit['att_k']} | 1st-Contact Win Rate: {audit['att_c1_pct']}% | {audit['att_xg']} xG ({audit['att_g']} Goals)",
                    f"Defending Set Pieces: {audit['def_k']} Faced | 1st-Contact Clear Rate: {audit['def_c1_pct']}% | {audit['def_xg']} xG Conceded ({audit['def_g']} Goals)",
                ]
                pm_kpis = [
                    ("Metric", "Attacking", "Defending"),
                    ("Set Pieces", str(audit["att_k"]), str(audit["def_k"])),
                    ("1st-Contact %", f"{audit['att_c1_pct']}%", f"{audit['def_c1_pct']}%"),
                    ("xG (Actual Goals)", f"{audit['att_xg']} ({audit['att_g']}G)", f"{audit['def_xg']} ({audit['def_g']}G)"),
                ]
                pm_pdf = f"exports/PostMatch_Audit_{own_team}_MW.pdf"
                pm_opp = (next(iter(own_matches_df["away_team"])) if next(iter(own_matches_df["home_team"])) == own_team else next(iter(own_matches_df["home_team"]))) if not own_matches_df.empty else "Opponent"
                build_matchday_pdf(pm_pdf, own_team, pm_opp, pm_att, pm_def, pm_takers, get_latest_team_hops(con, pm_opp).head(8), get_latest_team_hops(con, own_team).head(8), pm_bullets, pm_swg, pm_zon, pm_kpis)
                with open(pm_pdf, "rb") as f:
                    st.download_button("Download Post-Match Audit PDF", f, file_name=os.path.basename(pm_pdf), mime="application/pdf")
        render_team_dashboard(own_team, own_kicks_df, own_seq_df, own_faced_kicks, own_faced_seq)

    with tab3:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"**{opp_team} Takers & Long Throwers**")
            if not kicks_df.empty:
                kicks_df["Swing"] = kicks_df.apply(classify_corner_swing, axis=1)
                st.dataframe(kicks_df.groupby(["player", "pass_type", "Swing"]).size().reset_index(name="Deliveries").sort_values("Deliveries", ascending=False), use_container_width=True, hide_index=True)
            st.markdown(f"**{own_team} Takers & Long Throwers**")
            if not own_kicks_df.empty:
                own_kicks_df["Swing"] = own_kicks_df.apply(classify_corner_swing, axis=1)
                st.dataframe(own_kicks_df.groupby(["player", "pass_type", "Swing"]).size().reset_index(name="Deliveries").sort_values("Deliveries", ascending=False), use_container_width=True, hide_index=True)

        with col_b:
            st.markdown(f"**{opp_team} 1st, 2nd & 3rd+ Contact Receivers**")
            if not seq_df.empty:
                opp_c = seq_df[(seq_df["contact_number"].isin((1, 2, 3))) & (seq_df["team"] == opp_team)]
                st.dataframe(opp_c.groupby(["player", "contact_number"]).agg(Touches=("event_id", "count"), Total_xG=("shot_statsbomb_xg", "sum")).reset_index().sort_values(["contact_number", "Touches"], ascending=[True, False]), use_container_width=True, hide_index=True)
            st.markdown(f"**{own_team} 1st, 2nd & 3rd+ Contact Receivers**")
            if not own_seq_df.empty:
                own_c = own_seq_df[(own_seq_df["contact_number"].isin((1, 2, 3))) & (own_seq_df["team"] == own_team)]
                st.dataframe(own_c.groupby(["player", "contact_number"]).agg(Touches=("event_id", "count"), Total_xG=("shot_statsbomb_xg", "sum")).reset_index().sort_values(["contact_number", "Touches"], ascending=[True, False]), use_container_width=True, hide_index=True)

    with tab4:
        target_clip_team = st.radio("Select Team for Video Playlist", (opp_team, own_team), horizontal=True)
        c_kicks = kicks_df.copy() if target_clip_team == opp_team else own_kicks_df.copy()
        c_seq = seq_df if target_clip_team == opp_team else own_seq_df
        c_matches = opp_matches_df if target_clip_team == opp_team else own_matches_df

        if not c_kicks.empty:
            c_kicks["Box_Zone"] = c_kicks.apply(classify_box_zone, axis=1)
            c_kicks["Swing"] = c_kicks.apply(classify_corner_swing, axis=1)
            sp_xg = c_seq[c_seq["team"] == target_clip_team].groupby("set_piece_id")["shot_statsbomb_xg"].sum().reset_index(name="xG")
            sp_goal = c_seq[(c_seq["team"] == target_clip_team) & (c_seq["outcome"] == "Goal")].groupby("set_piece_id").size().reset_index(name="Goal")
            clip_df = c_kicks.merge(c_matches, on="match_id", how="left").merge(sp_xg, on="set_piece_id", how="left").merge(sp_goal, on="set_piece_id", how="left")
            clip_df["xG"] = clip_df["xG"].fillna(0.0).round(3)
            clip_df["Result"] = clip_df["Goal"].apply(lambda g: "GOAL" if pd.notna(g) and g > 0 else "No Goal")
            clip_df["Fixture"] = clip_df["home_team"] + " vs " + clip_df["away_team"]
            cols = ["match_date", "Fixture", "period", "timestamp", "pass_type", "Swing", "Box_Zone", "player", "xG", "Result"]
            clip_view = clip_df[cols].sort_values(["match_date", "period", "timestamp"], ascending=[False, True, True])
            st.dataframe(clip_view, use_container_width=True, hide_index=True)
            st.download_button(f"Download {target_clip_team} Clips CSV", clip_view.to_csv(index=False).encode("utf-8"), file_name=f"{target_clip_team}_SetPiece_Clips.csv", mime="text/csv")

    with tab5:
        st.subheader("Aerial Strength Comparison & Matchday PDF Export")
        st.pyplot(plot_aerial_mismatch(get_latest_team_hops(con, own_team), get_latest_team_hops(con, opp_team), own_team, opp_team))
        c_left, c_right = st.columns(2)
        own_hops = get_latest_team_hops(con, own_team)
        opp_hops = get_latest_team_hops(con, opp_team)
        with c_left:
            st.markdown(f"**{own_team} Top Aerial Players**")
            st.dataframe(own_hops, use_container_width=True, hide_index=True)
        with c_right:
            st.markdown(f"**{opp_team} Top Aerial Players**")
            st.dataframe(opp_hops, use_container_width=True, hide_index=True)

        if st.button("Generate Coach & Player Matchday PDF"):
            os.makedirs("exports", exist_ok=True)
            att_img = "exports/tmp_opp_att.png"
            def_img = "exports/tmp_opp_def.png"
            swg_img = "exports/tmp_opp_swg.png"
            own_img = "exports/tmp_own_att.png"
            plot_delivery_and_contacts(seq_df, show_contacts=(1, 3), title=f"{opp_team} 1st Contacts & Shots", save_path=att_img)
            plot_defensive_vulnerability(opp_faced_kicks, faced_seq_df, opp_team, save_path=def_img)
            plot_swing_deliveries(kicks_df, title=f"{opp_team} Delivery Swing Split", save_path=swg_img)
            plot_delivery_zone_heatmap(own_kicks_df, title=f"{own_team} Attacking Target Zones", save_path=own_img)
            takers_summary = kicks_df.groupby("player").size().reset_index(name="Kicks").sort_values("Kicks", ascending=False).head(6)
            briefs = generate_matchup_brief(own_team, opp_team, own_kicks_df, own_seq_df, kicks_df, seq_df, opp_faced_kicks, faced_seq_df, own_hops, opp_hops)
            own_xg = float(own_seq_df[(own_seq_df["team"] == own_team) & (own_seq_df["type"] == "Shot")]["shot_statsbomb_xg"].sum()) if not own_seq_df.empty else 0.0
            opp_xg = float(seq_df[(seq_df["team"] == opp_team) & (seq_df["type"] == "Shot")]["shot_statsbomb_xg"].sum()) if not seq_df.empty else 0.0
            kpis = [
                ("Metric", own_team[:10], opp_team[:10]),
                ("Total Set Pieces", str(len(own_kicks_df)), str(len(kicks_df))),
                ("Attacking xG", f"{own_xg:.2f}", f"{opp_xg:.2f}"),
                ("xG / 10 Set Pieces", f"{(own_xg/len(own_kicks_df)*10 if len(own_kicks_df) else 0):.2f}", f"{(opp_xg/len(kicks_df)*10 if len(kicks_df) else 0):.2f}"),
            ]
            pdf_path = f"exports/SetPiece_Report_{own_team}_vs_{opp_team}.pdf"
            build_matchday_pdf(pdf_path, own_team, opp_team, att_img, def_img, takers_summary, opp_hops.head(8), get_latest_team_hops(con, own_team).head(8), briefs, swg_img, own_img, kpis)
            with open(pdf_path, "rb") as f:
                st.download_button("Download Matchday PDF", f, file_name=os.path.basename(pdf_path), mime="application/pdf")



    with tab6:
        st.subheader(f"Automated Matchup Edge Brief: {own_team} vs {opp_team}")
        own_hops_b = get_latest_team_hops(con, own_team)
        opp_hops_b = get_latest_team_hops(con, opp_team)
        brief_bullets = generate_matchup_brief(
            own_team, opp_team, own_kicks_df, own_seq_df, kicks_df, seq_df, opp_faced_kicks, faced_seq_df, own_hops_b, opp_hops_b
        )
        for b in brief_bullets:
            st.info(b)

        st.markdown("---")
        st.subheader("Goal & High-xG Routine Sequence Visualizer")
        replay_team = st.radio("Select Team Routines to Replay", (opp_team, own_team), horizontal=True, key="replay_team")
        r_kicks = kicks_df if replay_team == opp_team else own_kicks_df
        r_seq = seq_df if replay_team == opp_team else own_seq_df
        r_matches = opp_matches_df if replay_team == opp_team else own_matches_df

        if not r_kicks.empty and not r_seq.empty:
            sp_xg = r_seq[r_seq["team"] == replay_team].groupby("set_piece_id")["shot_statsbomb_xg"].sum().reset_index(name="xG")
            sp_goal = r_seq[(r_seq["team"] == replay_team) & (r_seq["outcome"] == "Goal")].groupby("set_piece_id").size().reset_index(name="Goal")
            merged_r = r_kicks.merge(r_matches, on="match_id", how="left").merge(sp_xg, on="set_piece_id", how="left").merge(sp_goal, on="set_piece_id", how="left")
            merged_r["xG"] = merged_r["xG"].fillna(0.0)
            merged_r["IsGoal"] = merged_r["Goal"].fillna(0) > 0
            top_r = merged_r.sort_values(["IsGoal", "xG"], ascending=[False, False]).head(25)

            options = {}
            for _, row in top_r.iterrows():
                tag = "GOAL" if row["IsGoal"] else f"xG {row['xG']:.2f}"
                label = f"{tag} | {row['match_date']} {row['home_team']} vs {row['away_team']} ({row['timestamp']}) - {row['pass_type']} by {row['player']}"
                options[label] = row["set_piece_id"]

            chosen_label = st.selectbox("Select Goal or High-xG Routine to Diagram", list(options.keys()))
            chosen_sp_id = options[chosen_label]
            chosen_events = r_seq[r_seq["set_piece_id"] == chosen_sp_id].sort_values("index")

            col_diag, col_tbl = st.columns(2)
            with col_diag:
                st.pyplot(plot_routine_sequence(chosen_events, title=chosen_label))
            with col_tbl:
                st.markdown("**Step-by-Step Touch Chain**")
                chain_view = chosen_events[chosen_events["phase"].isin(("kick", "aftermath"))][
                    ["phase", "contact_number", "timestamp", "team", "player", "type", "outcome", "shot_statsbomb_xg"]
                ]
                st.dataframe(chain_view, use_container_width=True, hide_index=True)



        st.markdown("---")
        st.subheader("Off-Ball Screen Clusters & Near-Post Flick-On Detector")
        det_team = st.radio("Analyze Routine Patterns For", (opp_team, own_team), horizontal=True, key="det_team_radio")
        d_kicks = kicks_df if det_team == opp_team else own_kicks_df
        d_seq = seq_df if det_team == opp_team else own_seq_df
        rt_df, rt_sum = detect_routines_and_flicks(d_kicks, d_seq, det_team)

        if not rt_df.empty:
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Near-Post Flick Routines", rt_sum.get("near_post_flicks", 0), f"{rt_sum.get('flick_xg', 0.0)} xG")
            k2.metric("Off-Ball Screen / Hub Routines", rt_sum.get("screen_routines", 0), f"{rt_sum.get('screen_xg', 0.0)} xG")
            top_flicker = rt_df[rt_df["Routine_Pattern"].str.contains("Near-Post Flick")]["1st_Contact"].value_counts()
            k3.metric("Top Near-Post Flicker", str(next(iter(top_flicker.index))) if not top_flicker.empty else "-")
            top_2nd = rt_df[rt_df["Routine_Pattern"] != "Standard Central Delivery"]["2nd_Contact"].value_counts()
            top_2nd = top_2nd[top_2nd.index != "-"]
            k4.metric("Top 2nd-Contact Finisher", str(next(iter(top_2nd.index))) if not top_2nd.empty else "-")

            arch_tbl = rt_df.groupby("Routine_Pattern").agg(
                Frequency=("set_piece_id", "count"),
                Shots=("xG", lambda s: int((s > 0).sum())),
                Goals=("Goal", lambda s: int((s == "GOAL").sum())),
                Total_xG=("xG", lambda s: round(float(s.sum()), 2)),
            ).reset_index().sort_values("Total_xG", ascending=False)
            arch_tbl["xG / Routine"] = (arch_tbl["Total_xG"] / arch_tbl["Frequency"]).round(3)
            st.markdown(f"**{det_team} Tactical Routine Taxonomy Breakdown**")
            st.dataframe(arch_tbl, use_container_width=True, hide_index=True)

            c_rt1, c_rt2 = st.columns(2)
            with c_rt1:
                st.pyplot(plot_flick_and_screen_routines(rt_df, det_team))
            with c_rt2:
                st.markdown(f"**Detected {det_team} Set-Piece Routines (Flicks & Screens)**")
                flagged = rt_df[rt_df["Routine_Pattern"] != "Standard Central Delivery"][["timestamp", "pass_type", "Taker", "Routine_Pattern", "1st_Contact", "2nd_Contact", "xG", "Goal"]].sort_values("xG", ascending=False)
                st.dataframe(flagged, use_container_width=True, hide_index=True, height=410)

    with tab7:
        st.subheader("Premier League Set-Piece Library & 1st-Contact % Benchmarks")
        lb_df = get_league_benchmarks(con, sp_type)
        if not lb_df.empty:
            lb_df.insert(0, "Rank", range(1, len(lb_df) + 1))
            lb_df.insert(1, "Matchup", lb_df["team"].apply(lambda t: "OWN TEAM" if t == own_team else ("OPPOSITION" if t == opp_team else "-")))
            lb_df = lb_df.rename(columns={
                "team": "Club",
                "Set_Pieces": "Set Pieces",
                "First_Contact_Win_Pct": "1st-Contact Win %",
                "Total_xG_For": "Attacking xG",
                "Long_Throws": "Long Throws",
                "xG_per_10_SP": "xG / 10 SP",
            })
            st.dataframe(lb_df, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
