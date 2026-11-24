import os
import unicodedata
from fpdf import FPDF


def _clean(val):
    s = str(val or "")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


class MatchdayPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(11, 37, 69)
        self.cell(0, 7, "PREMIER LEAGUE - SET-PIECE SCOUTING REPORT", ln=True, align="L")
        self.set_draw_color(11, 37, 69)
        self.line(10, 17, 200, 17)
        self.ln(3)

    def footer(self):
        self.set_y(-11)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 7, f"Page {self.page_no()} | Tactical & Set-Piece Analysis Engine", align="C")


def _sec_bar(pdf, x, w, title):
    pdf.set_x(x)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(11, 37, 69)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(w, 5.5, f"  {_clean(title)}", ln=True, fill=True)
    pdf.set_text_color(20, 20, 20)


def build_matchday_pdf(
    output_pdf_path,
    own_team,
    opp_team,
    opp_att_chart_path,
    opp_def_chart_path,
    opp_takers_df,
    opp_hops_df,
    own_hops_df,
    brief_bullets=None,
    opp_swing_chart_path=None,
    own_att_chart_path=None,
    kpi_summary=None,
):
    pdf = MatchdayPDF()
    pdf.set_auto_page_break(auto=True, margin=12)

    # ================= PAGE 1: OPPOSITION SCOUTING =================
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 11.5)
    pdf.set_text_color(19, 64, 116)
    pdf.cell(0, 6, _clean(f"MATCHUP: {own_team.upper()} vs {opp_team.upper()}"), ln=True)

    if brief_bullets:
        pdf.set_fill_color(240, 244, 248)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(20, 20, 20)
        for b in brief_bullets:
            pdf.set_x(10)
        pdf.multi_cell(190, 4.3, f"- {_clean(b.replace('**', ''))}", fill=True)
        pdf.ln(2)

    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(0, 5, _clean(f"1. {opp_team} Attacking Set Pieces - Deliveries, Takers & Aerial Threats"), ln=True)
    pdf.ln(1)

    y1 = pdf.get_y()
    pdf.image(opp_att_chart_path, x=10, y=y1, w=95)

    pdf.set_xy(110, y1)
    _sec_bar(pdf, 110, 90, f"{opp_team} Primary Takers")
    if not opp_takers_df.empty:
        for _, r in opp_takers_df.head(6).iterrows():
            pdf.set_x(110)
            pdf.set_font("Helvetica", "", 8)
            t_name = _clean(r.get("player") or r.get("Player") or "")[:28]
            pdf.cell(62, 4.8, t_name, border=1)
            pdf.cell(28, 4.8, f"{r.get('Kicks', 0)} kicks", border=1, align="C", ln=True)

    pdf.ln(3)
    _sec_bar(pdf, 110, 90, f"{opp_team} Top Aerial Threats")
    if not opp_hops_df.empty:
        for idx, (_, r) in enumerate(opp_hops_df.head(8).iterrows()):
            pdf.set_x(110)
            pdf.set_font("Helvetica", "", 8)
            rk = f"#{r['#']}" if str(r.get("#", "-")) != "-" else f"{idx+1}."
            pdf.cell(12, 4.8, _clean(rk), border=1, align="C")
            pdf.cell(55, 4.8, _clean(r["Player"])[:26], border=1)
            pdf.cell(23, 4.8, f"{r['HOPS']}", border=1, align="C", ln=True)

    # Bottom Row Page 1: Swing Split + KPI Box
    y1_bot = max(pdf.get_y(), y1 + 74) + 3
    if opp_swing_chart_path and os.path.exists(opp_swing_chart_path):
        pdf.image(opp_swing_chart_path, x=10, y=y1_bot, w=95)

    if kpi_summary:
        pdf.set_xy(110, y1_bot)
        _sec_bar(pdf, 110, 90, "Set-Piece Efficiency Comparison")
        for label, own_v, opp_v in kpi_summary:
            pdf.set_x(110)
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(42, 5.2, _clean(label), border=1)
            pdf.cell(24, 5.2, _clean(own_v), border=1, align="C")
            pdf.cell(24, 5.2, _clean(opp_v), border=1, align="C", ln=True)

    # ================= PAGE 2: DEFENSIVE VULNERABILITY & OUR PLAN =================
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(19, 64, 116)
    pdf.cell(0, 6, _clean(f"2. {opp_team} Defensive Vulnerability & {own_team} Attacking Plan"), ln=True)
    pdf.ln(2)

    y2 = pdf.get_y()
    pdf.image(opp_def_chart_path, x=10, y=y2, w=95)

    pdf.set_xy(110, y2)
    _sec_bar(pdf, 110, 90, f"{own_team} Top Aerial Targets")
    if not own_hops_df.empty:
        for idx, (_, r) in enumerate(own_hops_df.head(8).iterrows()):
            pdf.set_x(110)
            pdf.set_font("Helvetica", "", 8)
            rk = f"#{r['#']}" if str(r.get("#", "-")) != "-" else f"{idx+1}."
            pdf.cell(12, 4.8, _clean(rk), border=1, align="C")
            pdf.cell(55, 4.8, _clean(r["Player"])[:26], border=1)
            pdf.cell(23, 4.8, f"{r['HOPS']}", border=1, align="C", ln=True)

    y2_bot = max(pdf.get_y(), y2 + 76) + 4
    if own_att_chart_path and os.path.exists(own_att_chart_path):
        pdf.set_xy(10, y2_bot - 5)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(0, 5, _clean(f"3. {own_team} Attacking Target Zones & Matchup Checklist"), ln=True)
        pdf.image(own_att_chart_path, x=10, y=pdf.get_y() + 1, w=95)

    pdf.set_xy(110, y2_bot + 1)
    _sec_bar(pdf, 110, 90, "Matchday Action Checklist")
    own_p1 = _clean(own_hops_df["Player"].iloc[0]) if not own_hops_df.empty else "Top Defender"
    opp_p1 = _clean(opp_hops_df["Player"].iloc[0]) if not opp_hops_df.empty else "Top Target"
    opp_t1 = _clean(opp_takers_df["player"].iloc[0]) if not opp_takers_df.empty else "Primary Taker"
    notes = (
        f"1. Aerial Assignment: {own_p1} marks {opp_p1} on all box deliveries.",
        f"2. Delivery Screen: Press/block {opp_t1} short & outswinging options.",
        "3. Edge Protection: Hold 2 blockers at D-arc for 2nd-phase clearances.",
        "4. Long Throws: Assign dedicated near-post flick-on sweeper.",
    )
    for n in notes:
        pdf.set_x(110)
        pdf.set_font("Helvetica", "", 8)
        pdf.multi_cell(90, 5.2, _clean(n), border=1)

    os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
    pdf.output(output_pdf_path)
    return output_pdf_path
