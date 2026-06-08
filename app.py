"""
app.py — BMS Estimation Review Tool (Streamlit)
───────────────────────────────────────────────
West 34th Street Hotel · M-200 Series

Tabs:
  1. Dashboard      — KPI cards, charts, quick status
  2. Scope Table    — aggregated by classification
  3. Discrepancies  — filterable, sortable, AI-resolvable
  4. Equipment Register — full filterable tag list + detail panel
  5. AI Scope Advisor  — per-device BMS point recommendations via Claude

Run:
    streamlit run app.py
"""

import json
import os
from pathlib import Path
from collections import defaultdict

import streamlit as st
import pandas as pd

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="BMS Estimation Review",
    page_icon="🏗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS overrides ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 2rem; }
.disc-high  { background:#fff3cd; border-left:4px solid #f59e0b; padding:8px 12px;
              border-radius:4px; margin-bottom:6px; }
.disc-med   { background:#e0f2fe; border-left:4px solid #0ea5e9; padding:8px 12px;
              border-radius:4px; margin-bottom:6px; }
.disc-low   { background:#f1f5f9; border-left:4px solid #94a3b8; padding:8px 12px;
              border-radius:4px; margin-bottom:6px; }
.tag-mono   { font-family: monospace; font-weight:600; font-size:0.9rem; }
.section-hdr{ font-size:0.75rem; font-weight:600; letter-spacing:0.06em;
              color:#64748b; text-transform:uppercase; margin-bottom:0.5rem; }
div[data-testid="stExpander"] summary { font-size:0.85rem; }
</style>
""", unsafe_allow_html=True)


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data
def load_data():
    """Load schedule ground truth and discrepancy report from output/ directory."""
    base = Path(__file__).parent / "output"
    sch_path = base / "schedule_ground_truth.json"
    rep_path = base / "discrepancy_report.json"
    soo_path = base / "soo_refs.json"

    # Fallback: look next to the script itself
    for p in [sch_path, Path("schedule_ground_truth.json")]:
        if p.exists():
            with open(p) as f:
                schedule = json.load(f)
            break
    else:
        schedule = _demo_schedule()

    report = None
    for p in [rep_path, Path("discrepancy_report.json")]:
        if p.exists():
            with open(p) as f:
                report = json.load(f)
            break

    soo = None
    for p in [soo_path, Path("soo_refs.json")]:
        if p.exists():
            with open(p) as f:
                soo = json.load(f)
            break

    return schedule, report, soo


def _demo_schedule():
    """Minimal demo data so app renders without any files present."""
    return {
        "project": "West 34th Street Hotel (demo)",
        "total_unique_tags": 0,
        "discrepancy_summary": {"in_schedule_not_in_soo": [], "soo_confirmed": [], "needs_review": []},
        "equipment": [],
    }


def get_status(e: dict) -> str:
    if e.get("discrepancy_flag") is True:
        return "Discrepancy"
    if e.get("soo_confirmed") is True:
        return "SOO confirmed"
    return "Needs review"


SEVERITY_COLOR = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "⚪"}
STATUS_COLOR   = {"SOO confirmed": "🟢", "Discrepancy": "🔴", "Needs review": "🟡"}


# ── Sidebar ───────────────────────────────────────────────────────────────────

def sidebar(schedule: dict, report: dict | None):
    with st.sidebar:
        st.markdown("### BMS Estimation Review")
        st.caption(schedule.get("project", "—"))
        st.caption(f"Drawing set: {', '.join(schedule.get('drawing_numbers', []))}")
        st.divider()

        if report:
            s = report.get("summary", {})
            st.metric("Total tags",       s.get("schedule_tags", 0))
            st.metric("SOO confirmed",    s.get("confirmed_both", 0))
            st.metric("Discrepancies",    s.get("in_schedule_not_soo", 0),
                      delta=f"{s.get('high_severity',0)} HIGH",
                      delta_color="inverse")
            st.metric("Needs review",     s.get("needs_review", 0))
        else:
            n = len(schedule.get("equipment", []))
            disc = schedule.get("discrepancy_summary", {})
            st.metric("Total tags",    n)
            st.metric("Discrepancies", len(disc.get("in_schedule_not_in_soo", [])))
            st.metric("SOO confirmed", len(disc.get("soo_confirmed", [])))
            st.metric("Needs review",  len(disc.get("needs_review", [])))

        st.divider()
        st.markdown('<p class="section-hdr">Files</p>', unsafe_allow_html=True)

        # Allow uploading fresh JSON
        uploaded = st.file_uploader("Upload schedule_ground_truth.json",
                                    type="json", key="upload_schedule")
        if uploaded:
            st.session_state["uploaded_schedule"] = json.load(uploaded)
            st.success("Schedule loaded from upload")

        st.divider()
        st.markdown("**API key** (for AI Advisor tab)")
        api_key = st.text_input("Anthropic API key", type="password",
                                value=os.environ.get("ANTHROPIC_API_KEY", ""),
                                key="api_key_input")
        if api_key:
            st.session_state["anthropic_api_key"] = api_key


# ── Tab 1: Dashboard ──────────────────────────────────────────────────────────

def tab_dashboard(schedule: dict, report: dict | None):
    equip = schedule.get("equipment", [])
    if not equip:
        st.info("No equipment data loaded. Upload schedule_ground_truth.json in the sidebar.")
        return

    disc_sum = schedule.get("discrepancy_summary", {})
    in_soo   = disc_sum.get("soo_confirmed", [])
    missing  = disc_sum.get("in_schedule_not_in_soo", [])
    review   = disc_sum.get("needs_review", [])

    # ── KPI row ───────────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total devices",    len(equip))
    k2.metric("SOO confirmed",    len(in_soo))
    k3.metric("Discrepancies",    len(missing), delta="need resolution", delta_color="inverse")
    k4.metric("Needs review",     len(review))
    k5.metric("Drawing sheets",   len(schedule.get("drawing_numbers", [])))

    st.divider()

    col_left, col_right = st.columns([1.2, 1])

    # ── Left: by classification bar chart ────────────────────────────────────
    with col_left:
        st.markdown("**Devices by classification**")
        cls_counts = defaultdict(lambda: {"total": 0, "confirmed": 0, "disc": 0, "review": 0})
        for e in equip:
            cls = e.get("classification", "Unknown")
            cls_counts[cls]["total"] += 1
            s = get_status(e)
            if s == "SOO confirmed":   cls_counts[cls]["confirmed"] += 1
            elif s == "Discrepancy":   cls_counts[cls]["disc"] += 1
            else:                      cls_counts[cls]["review"] += 1

        df_cls = pd.DataFrame([
            {"Classification": k, "Confirmed": v["confirmed"],
             "Discrepancy": v["disc"], "Review": v["review"]}
            for k, v in sorted(cls_counts.items())
        ])
        st.bar_chart(df_cls.set_index("Classification")[["Confirmed", "Discrepancy", "Review"]],
                     color=["#22c55e", "#f59e0b", "#94a3b8"])

    # ── Right: by floor donut-ish ────────────────────────────────────────────
    with col_right:
        st.markdown("**Status breakdown**")
        status_counts = {"SOO confirmed": len(in_soo),
                         "Discrepancy":   len(missing),
                         "Needs review":  len(review)}
        df_status = pd.DataFrame({
            "Status": list(status_counts.keys()),
            "Count":  list(status_counts.values()),
        })
        st.bar_chart(df_status.set_index("Status"), color=["#64748b"])

        st.divider()
        st.markdown("**Top discrepancy floors**")
        floor_disc = defaultdict(int)
        for e in equip:
            if e.get("discrepancy_flag"):
                floor_disc[e.get("floor", "?")] += 1
        if floor_disc:
            df_fl = pd.DataFrame({"Floor": list(floor_disc.keys()),
                                  "Issues": list(floor_disc.values())}) \
                      .sort_values("Issues", ascending=False)
            st.dataframe(df_fl, use_container_width=True, hide_index=True)


# ── Tab 2: Scope Table ────────────────────────────────────────────────────────

def tab_scope(schedule: dict):
    equip = schedule.get("equipment", [])
    if not equip:
        st.info("No data loaded.")
        return

    # Aggregate by classification
    agg = defaultdict(lambda: {
        "count": 0, "floors": set(), "bms": set(), "disc": 0, "confirmed": 0, "review": 0
    })
    for e in equip:
        cls = e.get("classification", "Unknown")
        agg[cls]["count"] += 1
        agg[cls]["floors"].add(e.get("floor", ""))
        bms_raw = e.get("bms_interface_default") or e.get("bms_interface") or ""
        agg[cls]["bms"].add(bms_raw.split(" ")[0] if bms_raw else "—")
        s = get_status(e)
        if s == "Discrepancy":   agg[cls]["disc"] += 1
        elif s == "SOO confirmed": agg[cls]["confirmed"] += 1
        else:                    agg[cls]["review"] += 1

    rows = []
    for cls, data in sorted(agg.items()):
        cat, _, sub = cls.partition(" / ")
        rows.append({
            "Category":        cat,
            "System type":     sub or cls,
            "Count":           data["count"],
            "SOO confirmed":   data["confirmed"],
            "Discrepancies":   data["disc"],
            "Needs review":    data["review"],
            "Floors":          ", ".join(sorted(f for f in data["floors"] if f)),
            "BMS interface":   ", ".join(sorted(b for b in data["bms"] if b and b != "—")),
        })

    df = pd.DataFrame(rows)

    # Highlight rows with issues
    def highlight_disc(row):
        if row["Discrepancies"] > 0:
            return ["background-color: #fff3cd"] * len(row)
        return [""] * len(row)

    st.markdown(f"**{len(equip)} devices across {len(agg)} classifications**")
    st.dataframe(
        df.style.apply(highlight_disc, axis=1),
        use_container_width=True,
        hide_index=True,
        height=600,
    )

    st.divider()
    st.download_button(
        "⬇ Download scope table (CSV)",
        df.to_csv(index=False),
        file_name="bms_scope_table.csv",
        mime="text/csv",
    )


# ── Tab 3: Discrepancies ─────────────────────────────────────────────────────

def tab_discrepancies(schedule: dict, report: dict | None):
    equip = schedule.get("equipment", [])
    discs = [e for e in equip if e.get("discrepancy_flag") is True]

    if not discs:
        # Fall back to report file
        if report:
            discs_raw = report.get("discrepancies", [])
            discs = [d for d in discs_raw if d.get("source_schedule")]
        if not discs:
            st.success("No discrepancies found.")
            return

    # Build a clean df from either source
    rows = []
    for d in discs:
        tag = d.get("tag", "")
        sys_name = d.get("system", "")
        cls      = d.get("classification", "")
        floor    = d.get("floor", "")
        action   = d.get("action", d.get("discrepancy_type", ""))
        severity = "HIGH" if any(x in tag for x in ["EUH", "UH-"]) else "MEDIUM"
        rows.append({
            "Sev":            SEVERITY_COLOR.get(severity, "⚪") + " " + severity,
            "Tag":            tag,
            "System":         sys_name,
            "Classification": cls,
            "Floor":          floor,
            "Issue":          d.get("issue", "in_schedule_not_in_soo"),
            "Action":         action,
        })

    df = pd.DataFrame(rows)

    # Filters
    c1, c2, c3 = st.columns([1, 1.5, 1.5])
    sev_filter = c1.selectbox("Severity", ["All", "HIGH", "MEDIUM", "LOW"])
    cls_filter = c2.selectbox("Classification", ["All"] + sorted(df["Classification"].unique().tolist()))
    fl_filter  = c3.selectbox("Floor", ["All"] + sorted(df["Floor"].unique().tolist()))

    filtered = df.copy()
    if sev_filter != "All":
        filtered = filtered[filtered["Sev"].str.contains(sev_filter)]
    if cls_filter != "All":
        filtered = filtered[filtered["Classification"] == cls_filter]
    if fl_filter != "All":
        filtered = filtered[filtered["Floor"] == fl_filter]

    st.markdown(f"**{len(filtered)} discrepancies** "
                f"({sum(1 for r in rows if 'HIGH' in r['Sev'])} HIGH, "
                f"{sum(1 for r in rows if 'MEDIUM' in r['Sev'])} MEDIUM, "
                f"{sum(1 for r in rows if 'LOW' in r['Sev'])} LOW)")

    # Callout for EUH/UH cluster
    euh_uh = [r for r in rows if "EUH" in r["Tag"] or r["Tag"].startswith("UH-")]
    if euh_uh:
        with st.expander(f"⚠️  {len(euh_uh)} unit heaters with no SOO sequence — click to review", expanded=True):
            st.markdown(
                "These devices appear in the M-200 schedule with **integral or standalone thermostats** "
                "and have **no BMS control sequence** in the SOO. This is the most common missed scope item "
                "in hotel BMS estimates. Confirm per device whether BMS monitoring is required."
            )
            cols = st.columns(4)
            for i, r in enumerate(euh_uh):
                with cols[i % 4]:
                    st.markdown(
                        f'<div class="disc-high">'
                        f'<span class="tag-mono">{r["Tag"]}</span><br>'
                        f'<small>{r["System"]}</small><br>'
                        f'<small style="color:#92400e">{r["Floor"]}</small>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    st.divider()

    # Main table
    st.dataframe(
        filtered[["Sev", "Tag", "System", "Floor", "Action"]],
        use_container_width=True,
        hide_index=True,
        height=380,
        column_config={
            "Sev":    st.column_config.TextColumn("Sev", width=80),
            "Tag":    st.column_config.TextColumn("Tag", width=120),
            "System": st.column_config.TextColumn("System", width=220),
            "Floor":  st.column_config.TextColumn("Floor", width=120),
            "Action": st.column_config.TextColumn("Action required"),
        },
    )

    st.divider()
    st.download_button(
        "⬇ Download discrepancy list (CSV)",
        filtered.to_csv(index=False),
        file_name="bms_discrepancies.csv",
        mime="text/csv",
    )


# ── Tab 4: Equipment Register ─────────────────────────────────────────────────

def tab_register(schedule: dict):
    equip = schedule.get("equipment", [])
    if not equip:
        st.info("No equipment data loaded.")
        return

    # Build flat df
    rows = []
    for e in equip:
        bms = e.get("bms_interface_default") or e.get("bms_interface") or "—"
        rows.append({
            "Tag":            e.get("tag", ""),
            "Floor":          e.get("floor", ""),
            "System":         e.get("system", ""),
            "Classification": e.get("classification", ""),
            "BMS interface":  bms,
            "Qty":            e.get("qty", "—"),
            "Status":         STATUS_COLOR.get(get_status(e), "⚪") + " " + get_status(e),
            "Notes":          e.get("notes", ""),
        })

    df = pd.DataFrame(rows)

    # Filters row
    c1, c2, c3, c4 = st.columns([2, 1.5, 1.5, 1.5])
    search   = c1.text_input("Search tag or system", placeholder="FCU-SC-5, pump, heat…")
    cls_f    = c2.selectbox("Classification", ["All"] + sorted(df["Classification"].unique().tolist()))
    floor_f  = c3.selectbox("Floor", ["All"] + sorted(df["Floor"].unique().tolist()))
    status_f = c4.selectbox("Status", ["All", "SOO confirmed", "Discrepancy", "Needs review"])

    filtered = df.copy()
    if search:
        mask = (df["Tag"].str.contains(search, case=False, na=False) |
                df["System"].str.contains(search, case=False, na=False))
        filtered = filtered[mask]
    if cls_f != "All":
        filtered = filtered[filtered["Classification"] == cls_f]
    if floor_f != "All":
        filtered = filtered[filtered["Floor"] == floor_f]
    if status_f != "All":
        filtered = filtered[filtered["Status"].str.contains(status_f)]

    st.markdown(f"**{len(filtered)} of {len(df)} devices**")

    # Highlight discrepancy rows
    def hl(row):
        if "Discrepancy" in row["Status"]:
            return ["background-color:#fff3cd"] * len(row)
        return [""] * len(row)

    selected_rows = st.dataframe(
        filtered.style.apply(hl, axis=1),
        use_container_width=True,
        hide_index=True,
        height=450,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Tag":    st.column_config.TextColumn("Tag", width=110),
            "Floor":  st.column_config.TextColumn("Floor", width=110),
            "System": st.column_config.TextColumn("System", width=200),
            "Status": st.column_config.TextColumn("Status", width=130),
            "Notes":  st.column_config.TextColumn("Notes"),
        },
    )

    # Detail panel for selected row
    sel = selected_rows.selection.rows if hasattr(selected_rows, "selection") else []
    if sel:
        idx = sel[0]
        row_tag = filtered.iloc[idx]["Tag"]
        rec = next((e for e in equip if e.get("tag") == row_tag), None)
        if rec:
            _device_detail_panel(rec)

    st.divider()
    st.download_button(
        "⬇ Download register (CSV)",
        filtered.to_csv(index=False),
        file_name="bms_equipment_register.csv",
        mime="text/csv",
    )


def _device_detail_panel(rec: dict):
    tag = rec.get("tag", "")
    status = get_status(rec)
    st.divider()
    h1, h2 = st.columns([3, 1])
    with h1:
        st.markdown(f"### `{tag}`  — {rec.get('system','')}")
    with h2:
        color = {"SOO confirmed": "green", "Discrepancy": "red", "Needs review": "orange"}[status]
        st.markdown(f"**Status:** :{color}[{status}]")

    if rec.get("discrepancy_flag"):
        st.warning(
            f"⚠️ **In schedule — not in SOO.** "
            f"{rec.get('action', 'Confirm BMS scope with engineer.')}"
        )

    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**Classification**  \n{rec.get('classification','—')}")
    c2.markdown(f"**Floor**  \n{rec.get('floor','—')}")
    c3.markdown(f"**BMS interface**  \n{rec.get('bms_interface_default') or rec.get('bms_interface','—')}")

    extras = {k: v for k, v in rec.items()
              if k not in ("tag","system","classification","floor","bms_interface",
                           "bms_interface_default","soo_confirmed","discrepancy_flag",
                           "discrepancy_type","action","notes","raw_line_sample","qty")
              and v is not None and v != "" and v != "Unknown"}
    if extras:
        with st.expander("Full spec data"):
            st.json(extras)

    if rec.get("notes"):
        st.info(f"📋 {rec.get('notes')}")

    if st.button(f"Get BMS scope for {tag} →", key=f"scope_{tag}"):
        st.session_state["ai_advisor_tag"] = tag
        st.session_state["ai_advisor_rec"] = rec
        st.info("Switched to AI Scope Advisor tab ↑")


# ── Tab 5: AI Scope Advisor ───────────────────────────────────────────────────

def tab_ai_advisor(schedule: dict):
    st.markdown("**AI Scope Advisor** — get BMS point lists and control sequences for any device")
    st.caption("Powered by Claude (Anthropic API). Add your API key in the sidebar.")

    equip = schedule.get("equipment", [])
    tags  = sorted([e.get("tag","") for e in equip if e.get("tag")])

    # Pre-populate if coming from register
    default_tag = st.session_state.get("ai_advisor_tag", tags[0] if tags else "")
    default_idx = tags.index(default_tag) if default_tag in tags else 0

    c1, c2 = st.columns([1.5, 1])
    with c1:
        selected_tag = st.selectbox("Select device tag", tags, index=default_idx)
    with c2:
        question_type = st.selectbox("Question type", [
            "What BMS control points are needed?",
            "What is the recommended control sequence?",
            "How should I handle this discrepancy?",
            "What are the integration requirements?",
            "Estimate labor hours for this device",
        ])

    rec = next((e for e in equip if e.get("tag") == selected_tag), {})

    # Show device context
    if rec:
        with st.expander(f"Device context: {selected_tag}", expanded=True):
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"**System:** {rec.get('system','—')}")
            c2.markdown(f"**Floor:** {rec.get('floor','—')}")
            c3.markdown(f"**Classification:** {rec.get('classification','—')}")
            if rec.get("discrepancy_flag"):
                st.warning("⚠️ Discrepancy: this device is in the schedule but **not in the SOO**.")

    custom_q = st.text_area(
        "Additional context or custom question (optional)",
        placeholder="e.g. This hotel uses Johnson Controls N2 field bus. The unit heater is in a back-of-house area…",
        height=80,
    )

    if st.button("Ask Claude →", type="primary", use_container_width=True):
        api_key = st.session_state.get("anthropic_api_key", os.environ.get("ANTHROPIC_API_KEY", ""))
        if not api_key:
            st.error("Add your Anthropic API key in the sidebar to use the AI Advisor.")
            return

        prompt = _build_prompt(selected_tag, rec, question_type, custom_q)
        with st.spinner("Claude is reviewing the scope…"):
            response = _call_claude(api_key, prompt)
        if response:
            st.markdown("---")
            st.markdown(response)
            st.divider()
            # Save to session for reference
            if "ai_history" not in st.session_state:
                st.session_state["ai_history"] = []
            st.session_state["ai_history"].append({
                "tag": selected_tag, "q": question_type, "a": response
            })

    # History
    if st.session_state.get("ai_history"):
        st.divider()
        st.markdown("**Previous queries this session**")
        for h in reversed(st.session_state["ai_history"][-5:]):
            with st.expander(f"{h['tag']} — {h['q'][:60]}"):
                st.markdown(h["a"])


def _build_prompt(tag: str, rec: dict, question: str, extra: str) -> str:
    system_type  = rec.get("system", "Unknown device")
    cls          = rec.get("classification", "Unknown")
    floor        = rec.get("floor", "Unknown")
    bms          = rec.get("bms_interface_default") or rec.get("bms_interface") or "Unknown"
    is_disc      = rec.get("discrepancy_flag", False)

    context = f"""Device: {tag}
System type: {system_type}
Classification: {cls}
Floor / location: {floor}
BMS interface: {bms}
SOO status: {"NOT FOUND IN SOO — discrepancy" if is_disc else "Confirmed in SOO"}
Project: West 34th Street Hotel (New York City hotel, mixed-use, 36-story)
"""
    if extra:
        context += f"\nAdditional context: {extra}"

    question_map = {
        "What BMS control points are needed?":
            "List the specific BMS monitoring and control points required for this device. "
            "For each point specify: point type (AI/AO/DI/DO/Network), description, units, and "
            "normal operating range. Format as a table.",
        "What is the recommended control sequence?":
            "Write a concise BMS control sequence of operation for this device, covering: "
            "startup/shutdown logic, setpoint control, alarm conditions, and any interlocks. "
            "Use standard BMS SOO format.",
        "How should I handle this discrepancy?":
            "This device appears in the mechanical schedule but has no SOO sequence. "
            "Explain what BMS scope is typically required for this device type, "
            "what questions to ask the engineer, and how to document the resolution.",
        "What are the integration requirements?":
            "Describe the BACnet/DDC integration requirements for this device: "
            "object types, instance numbers convention, required writable objects, "
            "and any vendor-specific integration notes.",
        "Estimate labor hours for this device":
            "Estimate BMS labor hours for this single device broken down by phase: "
            "engineering, programming, integration, graphics, startup/commissioning. "
            "Show your reasoning based on point count and complexity.",
    }

    q_text = question_map.get(question, question)

    return f"""You are a senior BMS (Building Management System) estimator and controls engineer with 20 years of NYC commercial hotel project experience.

{context}

Question: {q_text}

Be specific, practical, and concise. Use industry-standard terminology. If the device is a discrepancy (not in SOO), lead with the most important clarification question for the engineer before providing your recommendation."""


def _call_claude(api_key: str, prompt: str) -> str | None:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as e:
        st.error(f"Claude API error: {e}")
        return None


# ── Main app ──────────────────────────────────────────────────────────────────

def main():
    # Load data (from session upload or disk)
    if "uploaded_schedule" in st.session_state:
        schedule = st.session_state["uploaded_schedule"]
    else:
        schedule, report, soo = load_data()

    report = None
    soo    = None
    try:
        _, report, soo = load_data()
    except Exception:
        pass

    sidebar(schedule, report)

    st.title("BMS Estimation Review")
    st.caption(f"{schedule.get('project','—')} · "
               f"{schedule.get('total_unique_tags', len(schedule.get('equipment',[])))} devices · "
               f"Extracted {schedule.get('extraction_date','—')}")

    tabs = st.tabs(["📊 Dashboard", "📋 Scope Table",
                    "⚠️ Discrepancies", "🗂 Equipment Register",
                    "🤖 AI Scope Advisor"])

    with tabs[0]:
        tab_dashboard(schedule, report)
    with tabs[1]:
        tab_scope(schedule)
    with tabs[2]:
        tab_discrepancies(schedule, report)
    with tabs[3]:
        tab_register(schedule)
    with tabs[4]:
        tab_ai_advisor(schedule)


if __name__ == "__main__":
    main()
