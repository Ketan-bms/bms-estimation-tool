"""
app.py — BMS Estimation Review Tool (Streamlit) — Multi-Project Edition
────────────────────────────────────────────────────────────────────────
Upload any project's schedule_ground_truth.json to review it.
Bundled demo data (West 34th St Hotel) loads automatically on first visit.
"""

import json
import os
from pathlib import Path
from collections import defaultdict

import streamlit as st
import pandas as pd

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="BMS Estimation Tool",
    page_icon="🏗",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 2rem; }
.disc-high { background:#fff3cd; border-left:4px solid #f59e0b; padding:8px 12px; border-radius:4px; margin-bottom:6px; }
.tag-mono  { font-family: monospace; font-weight:600; font-size:0.9rem; }
.proj-card { background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:16px; margin-bottom:8px; cursor:pointer; }
.proj-card:hover { background:#f1f5f9; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_status(e):
    if e.get("discrepancy_flag") is True:  return "Discrepancy"
    if e.get("soo_confirmed") is True:     return "SOO confirmed"
    return "Needs review"

STATUS_COLOR = {"SOO confirmed":"🟢","Discrepancy":"🔴","Needs review":"🟡"}

def empty_project(name="New Project"):
    return {
        "project": name,
        "drawing_numbers": [],
        "total_unique_tags": 0,
        "extraction_date": "—",
        "discrepancy_summary": {"in_schedule_not_in_soo":[],"soo_confirmed":[],"needs_review":[]},
        "equipment": [],
    }

def project_stats(schedule):
    equip = schedule.get("equipment", [])
    disc  = schedule.get("discrepancy_summary", {})
    return {
        "total":       len(equip),
        "confirmed":   len(disc.get("soo_confirmed", [])),
        "discrepancy": len(disc.get("in_schedule_not_in_soo", [])),
        "review":      len(disc.get("needs_review", [])),
    }

@st.cache_data
def load_bundled_demo():
    """Load the West 34th St Hotel demo from files next to app.py."""
    for p in [Path("schedule_ground_truth.json"),
              Path(__file__).parent / "schedule_ground_truth.json"]:
        if p.exists():
            with open(p) as f:
                return json.load(f)
    return empty_project("West 34th Street Hotel (demo)")


# ── Session state bootstrap ───────────────────────────────────────────────────

def init_state():
    if "projects" not in st.session_state:
        demo = load_bundled_demo()
        st.session_state["projects"] = {"West 34th Street Hotel (demo)": demo}
        st.session_state["active_project"] = "West 34th Street Hotel (demo)"
    if "active_project" not in st.session_state:
        st.session_state["active_project"] = list(st.session_state["projects"].keys())[0]
    if "ai_history" not in st.session_state:
        st.session_state["ai_history"] = []


# ── Sidebar ───────────────────────────────────────────────────────────────────

def sidebar():
    with st.sidebar:
        st.markdown("## 🏗 BMS Estimation Tool")
        st.caption("Multi-project review dashboard")
        st.divider()

        # ── Project switcher ─────────────────────────────────────────────────
        st.markdown("**Projects**")
        projects = st.session_state["projects"]
        active   = st.session_state["active_project"]

        for name in list(projects.keys()):
            s = project_stats(projects[name])
            label = f"{'▶ ' if name == active else '   '}{name}"
            col1, col2 = st.columns([3, 1])
            with col1:
                if st.button(label, key=f"proj_btn_{name}", use_container_width=True):
                    st.session_state["active_project"] = name
                    st.rerun()
            with col2:
                st.caption(f"🔴{s['discrepancy']}" if s['discrepancy'] else f"✅{s['total']}")

        st.divider()

        # ── Upload new project ───────────────────────────────────────────────
        st.markdown("**Add a project**")
        project_name = st.text_input("Project name", placeholder="e.g. Empire State Bldg")
        uploaded = st.file_uploader(
            "Upload schedule_ground_truth.json",
            type="json",
            key="upload_new_project",
            help="Generate this file using schedule_extractor.py on your drawing PDFs"
        )
        if uploaded and project_name:
            if st.button("➕ Add project", type="primary", use_container_width=True):
                try:
                    data = json.load(uploaded)
                    data["project"] = project_name  # override with user-supplied name
                    st.session_state["projects"][project_name] = data
                    st.session_state["active_project"] = project_name
                    st.success(f"✅ {project_name} loaded — {len(data.get('equipment',[]))} devices")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not parse JSON: {e}")
        elif uploaded and not project_name:
            st.warning("Enter a project name first")

        # Remove project button
        if len(projects) > 1:
            if st.button("🗑 Remove current project", use_container_width=True):
                del st.session_state["projects"][active]
                st.session_state["active_project"] = list(st.session_state["projects"].keys())[0]
                st.rerun()

        st.divider()

        # ── API key ──────────────────────────────────────────────────────────
        st.markdown("**AI Scope Advisor**")
        api_key = st.text_input(
            "Anthropic API key", type="password",
            value=os.environ.get("ANTHROPIC_API_KEY", ""),
            key="api_key_input",
            help="Required for the AI Scope Advisor tab only"
        )
        if api_key:
            st.session_state["anthropic_api_key"] = api_key

        # ── Active project stats ─────────────────────────────────────────────
        st.divider()
        schedule = projects.get(active, empty_project())
        s = project_stats(schedule)
        st.caption(f"**{active}**")
        c1, c2 = st.columns(2)
        c1.metric("Devices",       s["total"])
        c1.metric("Confirmed",     s["confirmed"])
        c2.metric("Discrepancies", s["discrepancy"])
        c2.metric("Review",        s["review"])


# ── Tab 0: Project Overview (home) ────────────────────────────────────────────

def tab_overview():
    projects = st.session_state["projects"]

    st.markdown("### All projects")
    st.caption("Click a project in the sidebar to open it, or upload a new one below.")

    if not projects:
        st.info("No projects loaded yet. Upload a schedule_ground_truth.json in the sidebar.")
        return

    cols = st.columns(3)
    for i, (name, data) in enumerate(projects.items()):
        s = project_stats(data)
        with cols[i % 3]:
            active_badge = " ← active" if name == st.session_state["active_project"] else ""
            with st.container(border=True):
                st.markdown(f"**{name}**{active_badge}")
                st.caption(f"Drawing set: {', '.join(data.get('drawing_numbers', ['—']))}")
                st.caption(f"Extracted: {data.get('extraction_date','—')}")
                m1, m2, m3 = st.columns(3)
                m1.metric("Devices",      s["total"])
                m2.metric("🔴 Issues",   s["discrepancy"])
                m3.metric("🟡 Review",   s["review"])
                if st.button("Open →", key=f"open_{name}", use_container_width=True):
                    st.session_state["active_project"] = name
                    st.rerun()

    st.divider()
    st.markdown("#### How to add a project")
    st.markdown("""
1. Run `schedule_extractor.py --pdf YourDrawings.pdf --out output/` on your drawing set
2. This generates `schedule_ground_truth.json`
3. Enter a project name in the sidebar and upload that file
4. The full dashboard, discrepancy check, and AI advisor will work for that project instantly
    """)


# ── Tab 1: Dashboard ──────────────────────────────────────────────────────────

def tab_dashboard(schedule):
    equip    = schedule.get("equipment", [])
    disc_sum = schedule.get("discrepancy_summary", {})
    in_soo   = disc_sum.get("soo_confirmed", [])
    missing  = disc_sum.get("in_schedule_not_in_soo", [])
    review   = disc_sum.get("needs_review", [])

    if not equip:
        st.info("No equipment data. Upload a schedule_ground_truth.json for this project.")
        return

    k1,k2,k3,k4,k5 = st.columns(5)
    k1.metric("Total devices",  len(equip))
    k2.metric("SOO confirmed",  len(in_soo))
    k3.metric("Discrepancies",  len(missing), delta="need resolution", delta_color="inverse")
    k4.metric("Needs review",   len(review))
    k5.metric("Drawing sheets", len(schedule.get("drawing_numbers",[])))

    st.divider()
    col_left, col_right = st.columns([1.2,1])

    with col_left:
        st.markdown("**Devices by classification**")
        cls_counts = defaultdict(lambda:{"Confirmed":0,"Discrepancy":0,"Review":0})
        for e in equip:
            cls = e.get("classification","Unknown")
            s   = get_status(e)
            if s == "SOO confirmed":  cls_counts[cls]["Confirmed"] += 1
            elif s == "Discrepancy":  cls_counts[cls]["Discrepancy"] += 1
            else:                     cls_counts[cls]["Review"] += 1
        df_cls = pd.DataFrame([
            {"Classification":k, **v} for k,v in sorted(cls_counts.items())
        ])
        st.bar_chart(df_cls.set_index("Classification")[["Confirmed","Discrepancy","Review"]],
                     color=["#22c55e","#f59e0b","#94a3b8"])

    with col_right:
        st.markdown("**Status breakdown**")
        st.bar_chart(pd.DataFrame({
            "Status":["SOO confirmed","Discrepancy","Needs review"],
            "Count": [len(in_soo), len(missing), len(review)]
        }).set_index("Status"), color=["#64748b"])

        st.divider()
        st.markdown("**Top discrepancy floors**")
        floor_disc = defaultdict(int)
        for e in equip:
            if e.get("discrepancy_flag"):
                floor_disc[e.get("floor","?")] += 1
        if floor_disc:
            st.dataframe(
                pd.DataFrame({"Floor":list(floor_disc.keys()),
                              "Issues":list(floor_disc.values())})
                  .sort_values("Issues", ascending=False),
                use_container_width=True, hide_index=True
            )
        else:
            st.success("No floor-level discrepancies")


# ── Tab 2: Scope Table ────────────────────────────────────────────────────────

def tab_scope(schedule):
    equip = schedule.get("equipment", [])
    if not equip:
        st.info("No data."); return

    agg = defaultdict(lambda:{"count":0,"floors":set(),"bms":set(),"disc":0,"confirmed":0,"review":0})
    for e in equip:
        cls = e.get("classification","Unknown")
        agg[cls]["count"] += 1
        agg[cls]["floors"].add(e.get("floor",""))
        bms = (e.get("bms_interface_default") or e.get("bms_interface") or "")
        agg[cls]["bms"].add(bms.split(" ")[0] if bms else "—")
        s = get_status(e)
        if s=="Discrepancy":   agg[cls]["disc"] += 1
        elif s=="SOO confirmed": agg[cls]["confirmed"] += 1
        else:                  agg[cls]["review"] += 1

    rows = []
    for cls, d in sorted(agg.items()):
        cat,_,sub = cls.partition(" / ")
        rows.append({
            "Category": cat, "System type": sub or cls,
            "Count": d["count"], "SOO confirmed": d["confirmed"],
            "Discrepancies": d["disc"], "Needs review": d["review"],
            "Floors": ", ".join(sorted(f for f in d["floors"] if f)),
            "BMS interface": ", ".join(sorted(b for b in d["bms"] if b and b!="—")),
        })

    df = pd.DataFrame(rows)
    def hl(row):
        return ["background-color:#fff3cd"]*len(row) if row["Discrepancies"]>0 else [""]*len(row)

    st.markdown(f"**{len(equip)} devices · {len(agg)} classifications**")
    st.dataframe(df.style.apply(hl,axis=1), use_container_width=True, hide_index=True, height=550)
    st.download_button("⬇ Download scope CSV", df.to_csv(index=False),
                       file_name=f"scope_{schedule.get('project','project').replace(' ','_')}.csv")


# ── Tab 3: Discrepancies ──────────────────────────────────────────────────────

def tab_discrepancies(schedule):
    equip = schedule.get("equipment", [])
    discs = [e for e in equip if e.get("discrepancy_flag") is True]

    if not discs:
        st.success("✅ No discrepancies found for this project.")
        return

    rows = []
    for d in discs:
        tag = d.get("tag","")
        sev = "HIGH" if any(x in tag for x in ["EUH","UH-"]) else "MEDIUM"
        rows.append({
            "Sev":   ("🔴 HIGH" if sev=="HIGH" else "🟡 MEDIUM"),
            "Tag":   tag,
            "System": d.get("system",""),
            "Floor":  d.get("floor",""),
            "Action": d.get("action", d.get("notes","Verify BMS scope with engineer")),
        })

    df = pd.DataFrame(rows)

    c1,c2,c3 = st.columns([1,1.5,1.5])
    sev_f = c1.selectbox("Severity",["All","HIGH","MEDIUM"])
    cls_opts = ["All"] + sorted(set(d.get("classification","") for d in discs if d.get("classification")))
    cls_f = c2.selectbox("Classification", cls_opts)
    fl_opts = ["All"] + sorted(set(d.get("floor","") for d in discs if d.get("floor")))
    fl_f = c3.selectbox("Floor", fl_opts)

    filtered = df.copy()
    if sev_f  != "All": filtered = filtered[filtered["Sev"].str.contains(sev_f)]
    if cls_f  != "All":
        cls_tags = {d.get("tag") for d in discs if d.get("classification")==cls_f}
        filtered = filtered[filtered["Tag"].isin(cls_tags)]
    if fl_f   != "All": filtered = filtered[filtered["Floor"]==fl_f]

    # EUH/UH cluster callout
    euh_uh = [r for r in rows if "EUH" in r["Tag"] or r["Tag"].startswith("UH-")]
    if euh_uh:
        with st.expander(f"⚠️  {len(euh_uh)} unit heaters with no SOO sequence — click to review", expanded=True):
            st.markdown(
                "These devices are in the schedule with **integral/standalone thermostats** "
                "and have **no BMS control sequence** in the SOO. Most common missed scope item "
                "in hotel BMS estimates. Confirm per device whether BMS monitoring is required."
            )
            cols = st.columns(min(4, len(euh_uh)))
            for i, r in enumerate(euh_uh):
                with cols[i % 4]:
                    st.markdown(
                        f'<div class="disc-high"><span class="tag-mono">{r["Tag"]}</span><br>'
                        f'<small>{r["System"]}</small><br>'
                        f'<small style="color:#92400e">{r["Floor"]}</small></div>',
                        unsafe_allow_html=True
                    )

    st.divider()
    st.markdown(f"**{len(filtered)} discrepancies**")
    st.dataframe(
        filtered[["Sev","Tag","System","Floor","Action"]],
        use_container_width=True, hide_index=True, height=380,
        column_config={
            "Sev":    st.column_config.TextColumn("Sev", width=90),
            "Tag":    st.column_config.TextColumn("Tag", width=120),
            "System": st.column_config.TextColumn("System", width=220),
            "Floor":  st.column_config.TextColumn("Floor", width=120),
            "Action": st.column_config.TextColumn("Action required"),
        }
    )
    proj = schedule.get("project","project").replace(" ","_")
    st.download_button("⬇ Download CSV", filtered.to_csv(index=False),
                       file_name=f"discrepancies_{proj}.csv")


# ── Tab 4: Equipment Register ─────────────────────────────────────────────────

def tab_register(schedule):
    equip = schedule.get("equipment", [])
    if not equip:
        st.info("No equipment data."); return

    rows = []
    for e in equip:
        bms = e.get("bms_interface_default") or e.get("bms_interface") or "—"
        rows.append({
            "Tag":            e.get("tag",""),
            "Floor":          e.get("floor",""),
            "System":         e.get("system",""),
            "Classification": e.get("classification",""),
            "BMS interface":  bms,
            "Qty":            e.get("qty","—"),
            "Status":         STATUS_COLOR.get(get_status(e),"⚪")+" "+get_status(e),
        })
    df = pd.DataFrame(rows)

    c1,c2,c3,c4 = st.columns([2,1.5,1.5,1.5])
    search  = c1.text_input("Search tag or system", placeholder="FCU-SC-5, pump…")
    cls_f   = c2.selectbox("Classification", ["All"]+sorted(df["Classification"].unique().tolist()))
    floor_f = c3.selectbox("Floor",          ["All"]+sorted(df["Floor"].unique().tolist()))
    stat_f  = c4.selectbox("Status",         ["All","SOO confirmed","Discrepancy","Needs review"])

    filtered = df.copy()
    if search:
        mask = (df["Tag"].str.contains(search,case=False,na=False)|
                df["System"].str.contains(search,case=False,na=False))
        filtered = filtered[mask]
    if cls_f   != "All": filtered = filtered[filtered["Classification"]==cls_f]
    if floor_f != "All": filtered = filtered[filtered["Floor"]==floor_f]
    if stat_f  != "All": filtered = filtered[filtered["Status"].str.contains(stat_f)]

    def hl(row):
        return ["background-color:#fff3cd"]*len(row) if "Discrepancy" in row["Status"] else [""]*len(row)

    st.markdown(f"**{len(filtered)} of {len(df)} devices**")
    sel = st.dataframe(
        filtered.style.apply(hl,axis=1),
        use_container_width=True, hide_index=True, height=430,
        on_select="rerun", selection_mode="single-row",
        column_config={
            "Tag":    st.column_config.TextColumn("Tag", width=110),
            "Floor":  st.column_config.TextColumn("Floor", width=110),
            "System": st.column_config.TextColumn("System", width=200),
            "Status": st.column_config.TextColumn("Status", width=140),
        }
    )

    rows_sel = sel.selection.rows if hasattr(sel,"selection") else []
    if rows_sel:
        tag = filtered.iloc[rows_sel[0]]["Tag"]
        rec = next((e for e in equip if e.get("tag")==tag), None)
        if rec: _detail_panel(rec)

    proj = schedule.get("project","project").replace(" ","_")
    st.download_button("⬇ Download register CSV", filtered.to_csv(index=False),
                       file_name=f"register_{proj}.csv")


def _detail_panel(rec):
    tag    = rec.get("tag","")
    status = get_status(rec)
    st.divider()
    h1,h2 = st.columns([3,1])
    h1.markdown(f"### `{tag}` — {rec.get('system','')}")
    color = {"SOO confirmed":"green","Discrepancy":"red","Needs review":"orange"}[status]
    h2.markdown(f"**Status:** :{color}[{status}]")

    if rec.get("discrepancy_flag"):
        st.warning(f"⚠️ **In schedule — not in SOO.** {rec.get('action','Confirm BMS scope with engineer.')}")

    c1,c2,c3 = st.columns(3)
    c1.markdown(f"**Classification**  \n{rec.get('classification','—')}")
    c2.markdown(f"**Floor**  \n{rec.get('floor','—')}")
    c3.markdown(f"**BMS interface**  \n{rec.get('bms_interface_default') or rec.get('bms_interface','—')}")

    extras = {k:v for k,v in rec.items()
              if k not in ("tag","system","classification","floor","bms_interface",
                           "bms_interface_default","soo_confirmed","discrepancy_flag",
                           "discrepancy_type","action","notes","raw_line_sample","qty")
              and v not in (None,"","Unknown")}
    if extras:
        with st.expander("Full spec data"): st.json(extras)
    if rec.get("notes"):
        st.info(f"📋 {rec.get('notes')}")

    if st.button(f"Get AI scope for {tag} →", key=f"ai_{tag}"):
        st.session_state["ai_advisor_tag"] = tag
        st.session_state["ai_advisor_rec"] = rec
        st.info("Go to the AI Scope Advisor tab ↑")


# ── Tab 5: AI Scope Advisor ───────────────────────────────────────────────────

def tab_ai_advisor(schedule):
    st.markdown("**AI Scope Advisor** — BMS point lists, control sequences, and discrepancy resolution")
    st.caption("Powered by Claude · Add your Anthropic API key in the sidebar")

    equip = schedule.get("equipment", [])
    tags  = sorted([e.get("tag","") for e in equip if e.get("tag")])
    if not tags:
        st.info("No equipment data loaded for this project."); return

    default_tag = st.session_state.get("ai_advisor_tag", tags[0])
    default_idx = tags.index(default_tag) if default_tag in tags else 0

    c1,c2 = st.columns([1.5,1])
    selected_tag = c1.selectbox("Select device tag", tags, index=default_idx)
    question_type = c2.selectbox("Question type", [
        "What BMS control points are needed?",
        "What is the recommended control sequence?",
        "How should I handle this discrepancy?",
        "What are the integration requirements?",
        "Estimate labor hours for this device",
    ])

    rec = next((e for e in equip if e.get("tag")==selected_tag), {})
    if rec:
        with st.expander(f"Device context: {selected_tag}", expanded=True):
            c1,c2,c3 = st.columns(3)
            c1.markdown(f"**System:** {rec.get('system','—')}")
            c2.markdown(f"**Floor:** {rec.get('floor','—')}")
            c3.markdown(f"**Classification:** {rec.get('classification','—')}")
            if rec.get("discrepancy_flag"):
                st.warning("⚠️ Discrepancy: in schedule but **not in SOO**.")

    custom_q = st.text_area("Additional context (optional)",
        placeholder="e.g. Johnson Controls N2 bus, back-of-house location…", height=70)

    if st.button("Ask Claude →", type="primary", use_container_width=True):
        api_key = st.session_state.get("anthropic_api_key",
                                        os.environ.get("ANTHROPIC_API_KEY",""))
        if not api_key:
            st.error("Add your Anthropic API key in the sidebar.")
            return
        prompt = _build_prompt(selected_tag, rec, question_type, custom_q,
                               schedule.get("project","Unknown project"))
        with st.spinner("Claude is reviewing the scope…"):
            response = _call_claude(api_key, prompt)
        if response:
            st.markdown("---")
            st.markdown(response)
            st.session_state["ai_history"].append(
                {"project": schedule.get("project",""), "tag":selected_tag,
                 "q":question_type, "a":response})

    if st.session_state.get("ai_history"):
        st.divider()
        st.markdown("**Previous queries this session**")
        for h in reversed(st.session_state["ai_history"][-5:]):
            with st.expander(f"[{h.get('project','')}] {h['tag']} — {h['q'][:50]}"):
                st.markdown(h["a"])


def _build_prompt(tag, rec, question, extra, project_name):
    q_map = {
        "What BMS control points are needed?":
            "List the specific BMS monitoring and control points required. For each point: type (AI/AO/DI/DO/Network), description, units, normal range. Format as a table.",
        "What is the recommended control sequence?":
            "Write a concise BMS control sequence of operation covering: startup/shutdown logic, setpoint control, alarm conditions, and interlocks. Use standard SOO format.",
        "How should I handle this discrepancy?":
            "This device is in the schedule but has no SOO sequence. Explain typical BMS scope for this device type, what to ask the engineer, and how to document the resolution.",
        "What are the integration requirements?":
            "Describe BACnet/DDC integration requirements: object types, instance number convention, required writable objects, vendor-specific notes.",
        "Estimate labor hours for this device":
            "Estimate BMS labor hours broken down by: engineering, programming, integration, graphics, startup/commissioning. Show reasoning based on point count and complexity.",
    }
    return f"""You are a senior BMS estimator and controls engineer with 20 years of NYC commercial hotel project experience.

Device: {tag}
Project: {project_name}
System type: {rec.get('system','Unknown')}
Classification: {rec.get('classification','Unknown')}
Floor / location: {rec.get('floor','Unknown')}
BMS interface: {rec.get('bms_interface_default') or rec.get('bms_interface','Unknown')}
SOO status: {"NOT FOUND IN SOO — discrepancy" if rec.get('discrepancy_flag') else "Confirmed in SOO"}
{f"Additional context: {extra}" if extra else ""}

Question: {q_map.get(question, question)}

Be specific, practical, and concise. Use industry-standard terminology."""


def _call_claude(api_key, prompt):
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role":"user","content":prompt}]
        )
        return msg.content[0].text
    except Exception as e:
        st.error(f"Claude API error: {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    init_state()
    sidebar()

    active   = st.session_state["active_project"]
    projects = st.session_state["projects"]
    schedule = projects.get(active, empty_project())

    st.title("🏗 BMS Estimation Tool")
    st.caption(f"Active project: **{active}**  ·  "
               f"{schedule.get('total_unique_tags', len(schedule.get('equipment',[]))) or len(schedule.get('equipment',[]))} devices  ·  "
               f"Extracted {schedule.get('extraction_date','—')}")

    tabs = st.tabs(["🏠 Projects", "📊 Dashboard", "📋 Scope Table",
                    "⚠️ Discrepancies", "🗂 Equipment Register", "🤖 AI Scope Advisor"])

    with tabs[0]: tab_overview()
    with tabs[1]: tab_dashboard(schedule)
    with tabs[2]: tab_scope(schedule)
    with tabs[3]: tab_discrepancies(schedule)
    with tabs[4]: tab_register(schedule)
    with tabs[5]: tab_ai_advisor(schedule)


if __name__ == "__main__":
    main()
