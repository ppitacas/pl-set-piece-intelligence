import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from mplsoccer import VerticalPitch
from tactics import classify_corner_swing

CONTACT_COLORS = {
    0: "#1f77b4",
    1: "#ff7f0e",
    2: "#2ca02c",
    3: "#d62728",
}

SWING_COLORS = {
    "Inswinger": "#d62728",
    "Outswinger": "#1f77b4",
    "Short Corner": "#2ca02c",
    "Driven / Straight": "#ff7f0e",
    "Long Throw": "#7209b7",
    "Direct / Cross": "#008080",
    "Other / Unclassified": "#7f7f7f",
}


def plot_delivery_and_contacts(df_events, show_contacts=(1, 2, 3), title="Set-Piece Delivery & Contact Chain", save_path=None):
    pitch = VerticalPitch(pitch_type="statsbomb", half=True, pitch_color="#f8f9fa", line_color="#343a40")
    fig, ax = pitch.draw(figsize=(8, 6))

    kicks = df_events[df_events["contact_number"] == 0]
    for _, k in kicks.iterrows():
        if k["location_x"] and k["end_x"]:
            pitch.arrows(
                k["location_x"], k["location_y"], k["end_x"], k["end_y"],
                width=1.4, headwidth=4.5, color=CONTACT_COLORS.get(0), alpha=0.35, ax=ax
            )

    contact_configs = (
        (1, "1st Contact", "o", 70),
        (2, "2nd Contact", "^", 75),
        (3, "3rd+ Contact (Shots Only)", "*", 140),
    )

    for c_num, label, marker, size in contact_configs:
        if c_num not in show_contacts:
            continue
        sub = df_events[df_events["contact_number"] == c_num].dropna(subset=["location_x", "location_y"])
        if c_num == 3:
            sub = sub[sub["type"] == "Shot"]
        if not sub.empty:
            pitch.scatter(
                sub["location_x"], sub["location_y"],
                s=size, marker=marker, color=CONTACT_COLORS[c_num],
                edgecolors="black", linewidth=0.7, alpha=0.85,
                label=f"{label} ({len(sub)})", zorder=4, ax=ax
            )

    ax.legend(loc="lower left", frameon=True, facecolor="white", fontsize=8.5)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
    return fig


def plot_swing_deliveries(kicks_df, title="Delivery Types & Swing Split", save_path=None):
    pitch = VerticalPitch(pitch_type="statsbomb", half=True, pitch_color="#f8f9fa", line_color="#343a40")
    fig, ax = pitch.draw(figsize=(8, 6))

    df = kicks_df.copy()
    df["swing"] = df.apply(classify_corner_swing, axis=1)

    handles = []
    for swing_type, group in df.groupby("swing"):
        color = SWING_COLORS.get(swing_type, "#7f7f7f")
        handles.append(Patch(facecolor=color, label=f"{swing_type} ({len(group)})"))
        for _, k in group.iterrows():
            if k["location_x"] and k["end_x"]:
                pitch.arrows(
                    k["location_x"], k["location_y"], k["end_x"], k["end_y"],
                    width=1.8, headwidth=5, color=color, alpha=0.7, ax=ax
                )

    if handles:
        ax.legend(handles=handles, loc="lower left", frameon=True, facecolor="white", fontsize=8.5)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
    return fig


def plot_delivery_zone_heatmap(kicks_df, title="Target Delivery Zones Heatmap", save_path=None):
    pitch = VerticalPitch(pitch_type="statsbomb", half=True, pitch_color="#f8f9fa", line_color="#343a40")
    fig, ax = pitch.draw(figsize=(8, 6))

    valid = kicks_df.dropna(subset=["end_x", "end_y"])
    if not valid.empty:
        bin_stat = pitch.bin_statistic(valid["end_x"], valid["end_y"], statistic="count", bins=(12, 10))
        pitch.heatmap(bin_stat, ax=ax, cmap="Reds", edgecolors="#e0e0e0", alpha=0.75)
        pitch.label_heatmap(bin_stat, color="#1a1a1a", fontsize=9, fontweight="bold", ax=ax, ha="center", va="center", exclude_zeros=True)
        pitch.scatter(valid["end_x"], valid["end_y"], s=25, color="#0b2545", alpha=0.6, zorder=4, ax=ax)

    ax.set_title(f"{title} ({len(valid)} Deliveries)", fontsize=12, fontweight="bold", pad=10)
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
    return fig


def plot_defensive_vulnerability(faced_kicks_df, faced_seq_df, opp_team, save_path=None):
    pitch = VerticalPitch(pitch_type="statsbomb", half=True, pitch_color="#f8f9fa", line_color="#343a40")
    fig, ax = pitch.draw(figsize=(8, 6))

    valid = faced_kicks_df.dropna(subset=["end_x", "end_y"])
    if not valid.empty:
        bin_stat = pitch.bin_statistic(valid["end_x"], valid["end_y"], statistic="count", bins=(12, 10))
        pitch.heatmap(bin_stat, ax=ax, cmap="Blues", edgecolors="#e0e0e0", alpha=0.65)
        pitch.label_heatmap(bin_stat, color="#1a1a1a", fontsize=8.5, fontweight="bold", ax=ax, ha="center", va="center", exclude_zeros=True)

    if not faced_seq_df.empty:
        conceded_shots = faced_seq_df[(faced_seq_df["type"] == "Shot") & (faced_seq_df["team"] != opp_team)].dropna(subset=["location_x", "location_y"])
        non_goals = conceded_shots[conceded_shots["outcome"] != "Goal"]
        goals = conceded_shots[conceded_shots["outcome"] == "Goal"]

        if not non_goals.empty:
            pitch.scatter(
                non_goals["location_x"], non_goals["location_y"],
                s=non_goals["shot_statsbomb_xg"] * 350 + 60,
                color="#ff9f1c", edgecolors="black", linewidth=0.8, alpha=0.85,
                label=f"Shots Conceded ({len(non_goals)})", zorder=5, ax=ax
            )
        if not goals.empty:
            pitch.scatter(
                goals["location_x"], goals["location_y"],
                s=220, marker="*", color="#d62728", edgecolors="black", linewidth=1.0,
                label=f"Goals Conceded ({len(goals)})", zorder=6, ax=ax
            )

    ax.legend(loc="lower left", frameon=True, facecolor="white", fontsize=8.5)
    ax.set_title(f"{opp_team} Defending Vulnerability ({len(valid)} Faced)", fontsize=12, fontweight="bold", pad=10)
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
    return fig


def plot_360_tactical_setup(kick_row, frame_json, title="360 Defending Structure", save_path=None):
    pitch = VerticalPitch(pitch_type="statsbomb", half=True, pitch_color="#f8f9fa", line_color="#343a40")
    fig, ax = pitch.draw(figsize=(8, 6))
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
    return fig



def plot_goal_routines(seq_df, target_team, mode="for", title="Goals & Big Chances (Chained Routines)", save_path=None):
    pitch = VerticalPitch(pitch_type="statsbomb", half=True, pitch_color="#f8f9fa", line_color="#343a40")
    fig, ax = pitch.draw(figsize=(8, 6))

    if seq_df.empty:
        ax.set_title(title, fontsize=12, fontweight="bold")
        return fig

    shots = seq_df[seq_df["type"] == "Shot"].copy()
    shots = shots[shots["team"] == target_team] if mode == "for" else shots[shots["team"] != target_team]
    goals = shots[shots["outcome"] == "Goal"]
    premium = shots[(shots["outcome"] != "Goal") & (shots["shot_statsbomb_xg"] >= 0.12)]
    key_ids = set(goals["set_piece_id"]).union(set(premium["set_piece_id"]))

    for sp_id in key_ids:
        sub = seq_df[seq_df["set_piece_id"] == sp_id].sort_values("index")
        kick = sub[sub["contact_number"] == 0]
        c1 = sub[sub["contact_number"] == 1]
        shot = sub[sub["type"] == "Shot"].iloc[:1]

        if not kick.empty:
            k = kick.iloc[0]
            if pd.notna(k["location_x"]) and pd.notna(k["end_x"]):
                pitch.arrows(k["location_x"], k["location_y"], k["end_x"], k["end_y"], width=1.8, headwidth=5, color="#1d3557", alpha=0.75, zorder=2, ax=ax)

        if not c1.empty and not shot.empty:
            f1 = c1.iloc[0]
            s1 = shot.iloc[0]
            if f1["event_id"] != s1["event_id"] and pd.notna(f1["end_x"]) and pd.notna(s1["location_x"]):
                pitch.arrows(f1["location_x"], f1["location_y"], s1["location_x"], s1["location_y"], width=1.4, headwidth=4, color="#2a9d8f", lstyle="--", alpha=0.8, zorder=3, ax=ax)

    if not premium.empty:
        pitch.scatter(premium["location_x"], premium["location_y"], s=140, color="#ff9f1c", edgecolors="black", marker="o", label=f"Big Chance xG>=0.12 ({len(premium)})", zorder=5, ax=ax)

    if not goals.empty:
        pitch.scatter(goals["location_x"], goals["location_y"], s=260, color="#e63946", edgecolors="black", marker="*", label=f"Goal ({len(goals)})", zorder=6, ax=ax)

    handles, _ = ax.get_legend_handles_labels()
    handles.extend([Patch(facecolor="#1d3557", label="Delivery"), Patch(facecolor="#2a9d8f", label="1st Contact Lay-off / Flick")])
    ax.legend(handles=handles, loc="lower left", frameon=True, facecolor="white", fontsize=8.5)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
    return fig


def plot_routine_sequence(events_df, title="Goal / High-xG Routine Chain", save_path=None):
    pitch = VerticalPitch(pitch_type="statsbomb", half=True, pitch_color="#f8f9fa", line_color="#343a40")
    fig, ax = pitch.draw(figsize=(8, 6))

    key_types = {"Pass", "Shot", "Clearance", "Duel", "Interception", "Goal Keeper"}
    seq = events_df[(events_df["phase"].isin(("kick", "aftermath"))) & (events_df["type"].isin(key_types))].sort_values("index")

    shots_only = seq[seq["type"] == "Shot"]
    if not shots_only.empty:
        first_shot_idx = int(shots_only["index"].min())
        seq = seq[seq["index"] <= first_shot_idx]

    step = 0
    for _, ev in seq.iterrows():
        lx, ly = ev.get("location_x"), ev.get("location_y")
        ex, ey = ev.get("end_x"), ev.get("end_y")
        if lx is None or pd.isna(lx):
            continue
        step += 1
        is_kick = ev.get("phase") == "kick"
        is_shot = ev.get("type") == "Shot"
        is_goal = ev.get("outcome") == "Goal"

        color = "#d62728" if is_goal else ("#ff9f1c" if is_shot else ("#1d3557" if is_kick else "#2a9d8f"))
        marker_sym = "*" if is_goal else ("D" if is_shot else "o")
        size = 240 if is_goal else (130 if is_shot else 95)

        if ex is not None and pd.notna(ex):
            pitch.arrows(
                lx, ly, ex, ey,
                width=2.0 if is_kick else 1.5,
                headwidth=5.5,
                color=color,
                linestyle="-" if is_kick else "--",
                alpha=0.85,
                zorder=3,
                ax=ax,
            )

        pitch.scatter(lx, ly, s=size, marker=marker_sym, color=color, edgecolors="black", zorder=5, ax=ax)
        last_name = str(ev.get("player", "")).split()[-1]
        ax.text(ly, lx - 1.5, f"{step}. {last_name}", fontsize=8.5, fontweight="bold", ha="center",
                bbox=dict(boxstyle="round,pad=0.15", facecolor="white", alpha=0.8, edgecolor="none"), zorder=6)

    ax.set_title(title, fontsize=11, fontweight="bold", pad=10)
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
    return fig




def plot_aerial_mismatch(own_hops_df, opp_hops_df, own_team, opp_team, save_path=None):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.6))
    fig.patch.set_facecolor("#ffffff")

    if own_hops_df.empty or opp_hops_df.empty:
        fig.suptitle(f"Aerial Strength Comparison: {own_team} vs {opp_team}", fontweight="bold")
        return fig

    own_sub = own_hops_df.head(12).sort_values("HOPS", ascending=True).reset_index(drop=True)
    opp_sub = opp_hops_df.head(12).sort_values("HOPS", ascending=True).reset_index(drop=True)

    # First Panel (Left): Our Team
    y1 = range(len(own_sub))
    bars1 = ax1.barh(y1, own_sub["HOPS"], color="#1d3557", height=0.62)
    ax1.axvline(0.50, color="#6c757d", linestyle="--", linewidth=1.1, zorder=4)
    ax1.set_xlim(0.0, 1.0)
    ax1.set_yticks(list(y1))
    ax1.set_yticklabels([f"#{r['#']} {r['Player']}" for _, r in own_sub.iterrows()], fontsize=9, fontweight="bold", color="#111111")
    ax1.set_xlabel("Hudl HOPS (0–1)", fontsize=9, fontweight="bold", color="#1d3557")
    ax1.set_title(f"1. {own_team} (Our Team)", fontsize=11, fontweight="bold", color="#1d3557", pad=8)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.grid(axis="x", linestyle=":", alpha=0.45)

    for bar, val in zip(bars1, own_sub["HOPS"]):
        ax1.text(min(0.95, float(val) + 0.02), bar.get_y() + bar.get_height() / 2, f"{float(val):.2f}", va="center", ha="left", fontsize=8.5, fontweight="bold", color="#1d3557")

    # Second Panel (Right): Opposition Team
    y2 = range(len(opp_sub))
    bars2 = ax2.barh(y2, opp_sub["HOPS"], color="#e63946", height=0.62)
    ax2.axvline(0.50, color="#6c757d", linestyle="--", linewidth=1.1, zorder=4)
    ax2.set_xlim(0.0, 1.0)
    ax2.set_yticks(list(y2))
    ax2.set_yticklabels([f"#{r['#']} {r['Player']}" for _, r in opp_sub.iterrows()], fontsize=9, fontweight="bold", color="#111111")
    ax2.set_xlabel("Hudl HOPS (0–1)", fontsize=9, fontweight="bold", color="#e63946")
    ax2.set_title(f"2. {opp_team} (Opposition)", fontsize=11, fontweight="bold", color="#e63946", pad=8)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.grid(axis="x", linestyle=":", alpha=0.45)

    for bar, val in zip(bars2, opp_sub["HOPS"]):
        ax2.text(min(0.95, float(val) + 0.02), bar.get_y() + bar.get_height() / 2, f"{float(val):.2f}", va="center", ha="left", fontsize=8.5, fontweight="bold", color="#e63946")

    fig.suptitle(f"Aerial Strength Comparison (Hudl HOPS 0–1 | Dashed = 0.50 League Avg)", fontsize=12, fontweight="bold", color="#111111", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
    return fig


def plot_flick_and_screen_routines(routines_df, team_name):
    pitch = VerticalPitch(pitch_type="statsbomb", half=True, pitch_color="#f8f9fa", line_color="#343a40")
    fig, ax = pitch.draw(figsize=(8, 6))

    if routines_df.empty:
        ax.set_title(f"{team_name} — Near-Post Flicks & Screen Clusters", fontsize=12, fontweight="bold")
        return fig

    flicks = routines_df[routines_df["Routine_Pattern"].str.contains("Near-Post Flick", na=False)]
    screens = routines_df[routines_df["Routine_Pattern"].str.contains("Screen", na=False)]

    if not screens.empty:
        pitch.scatter(screens["c1_x"], screens["c1_y"], s=110, color="#457b9d", alpha=0.65, edgecolors="black", label=f"Box Screen / Cluster Hub ({len(screens)})", zorder=3, ax=ax)
        s_arrows = screens.dropna(subset=["c2_x", "c2_y"])
        for _, r in s_arrows.iterrows():
            pitch.arrows(r["c1_x"], r["c1_y"], r["c2_x"], r["c2_y"], width=1.6, headwidth=5, color="#457b9d", alpha=0.75, zorder=4, ax=ax)

    if not flicks.empty:
        pitch.scatter(flicks["c1_x"], flicks["c1_y"], s=140, marker="^", color="#e63946", edgecolors="black", label=f"Near-Post 1st Contact ({len(flicks)})", zorder=5, ax=ax)
        f_arrows = flicks.dropna(subset=["c2_x", "c2_y"])
        for _, r in f_arrows.iterrows():
            pitch.arrows(r["c1_x"], r["c1_y"], r["c2_x"], r["c2_y"], width=2.0, headwidth=6, color="#e63946", alpha=0.9, zorder=6, ax=ax)

    ax.legend(loc="lower left", frameon=True, facecolor="white", fontsize=8.5)
    ax.set_title(f"{team_name} — Near-Post Flick-Ons & Screen Routine Vectors", fontsize=11.5, fontweight="bold", pad=10)
    plt.tight_layout()
    return fig
