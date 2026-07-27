"""
BMS Estimation Tool — app.py v2
Complete multi-project estimating platform.
Run: streamlit run app.py
"""

import json, os, io, base64
from material_module import module_material, init_pricebooks
from markup_ui import module_markup
from pdf_takeoff import run_pdf_takeoff, takeoff_to_session_format
from pathlib import Path
from datetime import date
from collections import defaultdict

import streamlit as st
import pandas as pd

st.set_page_config(page_title="BMS Estimator", page_icon="🏗", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
[data-testid="stMetricValue"]{font-size:1.8rem}
.block-label{font-size:.7rem;font-weight:600;letter-spacing:.06em;color:#64748b;text-transform:uppercase;margin-bottom:.3rem}
.disc-banner{background:#fff3cd;border-left:4px solid #f59e0b;padding:10px 14px;border-radius:0 6px 6px 0;margin-bottom:8px}
.chip-done{background:#dcfce7;color:#166534;font-size:11px;padding:2px 8px;border-radius:4px;font-weight:500}
.chip-prog{background:#dbeafe;color:#1e40af;font-size:11px;padding:2px 8px;border-radius:4px;font-weight:500}
.chip-issue{background:#fef9c3;color:#854d0e;font-size:11px;padding:2px 8px;border-radius:4px;font-weight:500}
.chip-empty{background:#f1f5f9;color:#64748b;font-size:11px;padding:2px 8px;border-radius:4px;border:0.5px solid #e2e8f0}
</style>
""", unsafe_allow_html=True)

DEFAULT_RATES = {"Engineering":95,"Programming":85,"Integration":75,"Graphics":70,"Startup":80}
PHASES = list(DEFAULT_RATES.keys())
MODULE_ORDER = ["Takeoff","Point List","Estimate","Proposal"]

# ── State ─────────────────────────────────────────────────────────────────────
# ── Persistent storage using st.cache_resource ────────────────────────────────
# Survives browser refresh for the lifetime of the Streamlit server process.
# Clients (including template bytes) and project metadata are stored here.
# Uploaded PDFs are NOT stored (too large) — must re-upload after server restart.

@st.cache_resource
def _get_store():
    """One shared dict that persists across reruns and refreshes."""
    return {
        "clients":   {},   # client metadata (rates, template names)
        "projects":  {},   # project metadata (no doc bytes)
        "templates": {},   # client template bytes keyed by "{client}_pl" / "{client}_prop"
    }


def _save_app_state():
    """Write current session state into the persistent store."""
    store = _get_store()
    try:
        # ── Clients ───────────────────────────────────────────────────────
        clients_meta = {}
        for cname, c in st.session_state.get("clients", {}).items():
            meta = {k: v for k, v in c.items()
                    if k not in ("pl_template_bytes", "prop_template_bytes")}
            # Store template bytes separately
            if c.get("pl_template_bytes"):
                store["templates"][f"{cname}_pl"]   = c["pl_template_bytes"]
            if c.get("prop_template_bytes"):
                store["templates"][f"{cname}_prop"] = c["prop_template_bytes"]
            clients_meta[cname] = meta
        store["clients"] = clients_meta

        # ── Projects (no doc bytes) ───────────────────────────────────────
        projects_meta = {}
        for pname, p in st.session_state.get("projects", {}).items():
            projects_meta[pname] = {
                k: v for k, v in p.items() if k not in ("docs",)
            }
            projects_meta[pname].setdefault("docs", {})
            projects_meta[pname]["doc_names"] = p.get("doc_names", {})
        store["projects"] = projects_meta

    except Exception:
        pass


def _load_app_state():
    """Read from persistent store into session state (only if not already loaded)."""
    store = _get_store()
    try:
        # ── Clients ───────────────────────────────────────────────────────
        for cname, meta in store.get("clients", {}).items():
            if cname not in st.session_state["clients"]:
                entry = dict(meta)
                pl_b   = store["templates"].get(f"{cname}_pl")
                prop_b = store["templates"].get(f"{cname}_prop")
                if pl_b:   entry["pl_template_bytes"]   = pl_b
                if prop_b: entry["prop_template_bytes"] = prop_b
                st.session_state["clients"][cname] = entry

        # ── Projects ──────────────────────────────────────────────────────
        for pname, meta in store.get("projects", {}).items():
            if pname not in st.session_state["projects"]:
                entry = dict(meta)
                entry.setdefault("docs", {})
                entry.setdefault("doc_names", {})
                st.session_state["projects"][pname] = entry

    except Exception:
        pass


def init():
    defaults = {
        "clients":{}, "projects":{},
        "active_project":None, "active_module":"Takeoff",
        "nav":"Overview", "ai_history":[],
        "storage_loaded": False,
    }
    for k,v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Load persisted data on first run (from cache_resource store)
    if not st.session_state.get("storage_loaded"):
        _load_app_state()
        st.session_state["storage_loaded"] = True

def new_project(name, client, bid_date, address):
    return {
        "name":name,"client":client,"bid_date":bid_date,
        "address":address,"created":str(date.today()),
        "docs":{},"doc_names":{},
        "takeoff":{"equipment":[],"discrepancies":[],"status":"not_started"},
        "point_list":{"rows":[],"status":"not_started"},
        "estimate":{"lines":[],"rates":{},"markup":10,"status":"not_started"},
        "proposal":{"text":"","status":"not_started"},
    }

def module_status(p, mod):
    return p[mod.lower().replace(" ","_")]["status"]

def module_locked(p, mod):
    """New unlock rules — modules open based on available docs, not chain."""
    if mod == "Takeoff":
        return False   # always open
    if mod == "Point List":
        # Unlocks when SOO or controls spec is uploaded
        return not (p["docs"].get("SOO") or p["docs"].get("Controls spec"))
    if mod == "Estimate":
        # Unlocks when point list has rows OR controls spec uploaded
        has_points = len(p["point_list"].get("rows", [])) > 0
        has_spec   = bool(p["docs"].get("Controls spec") or p["docs"].get("SOO"))
        return not (has_points or has_spec)
    if mod == "Proposal":
        # Unlocks when estimate has lines OR takeoff is done
        has_estimate = len(p["estimate"].get("lines", [])) > 0
        has_takeoff  = p["takeoff"]["status"] != "not_started"
        return not (has_estimate or has_takeoff)
    return False  # AI Advisor, Drawing Markup always open


def module_data_warning(p, mod):
    """Return warning text when module is open but missing some data."""
    has_takeoff  = p["takeoff"]["status"] != "not_started"
    has_points   = len(p["point_list"].get("rows", [])) > 0
    has_estimate = len(p["estimate"].get("lines", [])) > 0
    has_soo      = bool(p["docs"].get("SOO"))
    has_spec     = bool(p["docs"].get("Controls spec"))

    if mod == "Point List" and not has_takeoff:
        return ("ℹ️ No takeoff loaded — point list will be generated from SOO/spec only. "
                "Load takeoff for exact device tags.")
    if mod == "Estimate" and not has_points:
        return ("ℹ️ No point list yet — estimate will use rough point counts from SOO/spec. "
                "Generate a point list first for more accurate hours.")
    if mod == "Estimate" and not has_takeoff:
        return ("ℹ️ No takeoff loaded — material quantities are estimated, not from drawings. "
                "Load takeoff for accurate device counts.")
    if mod == "Proposal" and not has_takeoff:
        return ("ℹ️ No takeoff loaded — proposal will use SOO-based scope only. "
                "Load takeoff to auto-fill Clarifications and Exclusions with real device tags.")
    if mod == "Proposal" and not has_estimate:
        return ("ℹ️ No estimate yet — proposal will not include a price. "
                "Generate estimate first to include pricing.")
    return None

def chip(s, label):
    cls = {"done":"chip-done","in_progress":"chip-prog",
           "issues":"chip-issue"}.get(s,"chip-empty")
    return f'<span class="{cls}">{label}</span>'

def get_status(e):
    if e.get("discrepancy_flag"): return "Discrepancy"
    if e.get("soo_confirmed"):    return "SOO confirmed"
    return "Needs review"

def api_key():
    return st.session_state.get("anthropic_api_key",
                                 os.environ.get("ANTHROPIC_API_KEY",""))

# ── Sidebar ───────────────────────────────────────────────────────────────────
def sidebar():
    with st.sidebar:
        st.markdown("## 🏗 BMS Estimator")
        st.caption(f"FY {date.today().year}")
        st.divider()

        # ── Top nav ───────────────────────────────────────────────────
        for label in ["Overview", "Projects", "Reports"]:
            active = (st.session_state.nav == label and
                      (label != "Projects" or not st.session_state.active_project))
            if st.button(label, key=f"nav_{label}",
                         type="primary" if active else "secondary",
                         use_container_width=True):
                st.session_state.nav = label
                if label != "Projects":
                    st.session_state.active_project = None
                else:
                    st.session_state.active_project = None
                st.rerun()

        # ── Project sub-branches ──────────────────────────────────────
        if st.session_state.projects:
            st.divider()

            MODULES_NAV = [
                ("📐", "Takeoff"),
                ("📋", "Point List"),
                ("💰", "Estimate"),
                ("📄", "Proposal"),
                ("🖊",  "Drawing Markup"),
                ("🤖", "AI Advisor"),
            ]

            for pname, p in st.session_state.projects.items():
                disc     = len(p["takeoff"].get("discrepancies", []))
                is_open  = st.session_state.active_project == pname
                proj_label = f"▶ {pname}" if is_open else pname

                # Project name button
                if st.button(proj_label,
                             key=f"sb_proj_{pname}",
                             use_container_width=True,
                             type="primary" if is_open else "secondary"):
                    st.session_state.active_project = pname
                    st.session_state.active_module  = "Takeoff"
                    st.session_state.nav            = "Projects"
                    st.rerun()

                # Sub-tasks — only show when project is open
                if is_open:
                    for icon, mod in MODULES_NAV:
                        is_active_mod = st.session_state.active_module == mod

                        # Status indicator
                        s = p.get(mod.lower().replace(" ","_"), {})
                        if isinstance(s, dict):
                            status = s.get("status", "not_started")
                        else:
                            status = "not_started"
                        dot = ("🟢" if status == "done" else
                               "🟡" if status == "in_progress" else
                               "🔴" if (mod == "Takeoff" and disc) else "⚪")

                        # Indent + style
                        btn_label = f"  {icon} {mod}"
                        btn_style = "primary" if is_active_mod else "secondary"

                        # Use markdown for indented look
                        col_indent, col_btn = st.columns([0.12, 0.88])
                        col_indent.markdown(
                            f'<div style="text-align:right;padding-top:6px;'
                            f'font-size:9px;color:#cbd5e1">{"│"}</div>',
                            unsafe_allow_html=True)
                        if col_btn.button(
                            f"{dot} {mod}",
                            key=f"sb_mod_{pname}_{mod}",
                            use_container_width=True,
                            type=btn_style
                        ):
                            st.session_state.active_project = pname
                            st.session_state.active_module  = mod
                            st.session_state.nav            = "Projects"
                            st.rerun()

                    if disc:
                        st.caption(f"    ⚠️ {disc} discrepancies")

                st.markdown("")  # spacing between projects

        st.divider()
        k = st.text_input("Anthropic API key", type="password",
                          value=os.environ.get("ANTHROPIC_API_KEY", ""),
                          key="api_key_input")
        if k: st.session_state["anthropic_api_key"] = k

# ── Overview ──────────────────────────────────────────────────────────────────
def page_overview():
    today    = date.today()
    projects = st.session_state.projects

    # ── Styles ────────────────────────────────────────────────────────────
    st.markdown("""<style>
    .kpi { background:#fff; border:1px solid #e2e8f0; border-radius:12px;
           padding:20px 18px; text-align:center; }
    .kpi-icon  { font-size:24px; margin-bottom:6px; }
    .kpi-val   { font-size:2rem; font-weight:700; color:#1e293b; line-height:1.1; }
    .kpi-label { font-size:11px; font-weight:600; color:#64748b;
                 text-transform:uppercase; letter-spacing:.06em; margin-top:6px; }
    .kpi-sub   { font-size:11px; color:#94a3b8; margin-top:3px; }
    .pcard { background:#fff; border:1px solid #e2e8f0; border-radius:12px;
             padding:16px 18px; margin-bottom:10px; }
    .pcard-name { font-size:15px; font-weight:600; color:#1e293b; }
    .pcard-meta { font-size:12px; color:#64748b; margin:3px 0 10px; }
    .pill { display:inline-block; font-size:10px; padding:2px 8px;
            border-radius:4px; margin-right:4px; font-weight:500; }
    .pill-done  { background:#dcfce7; color:#166534; }
    .pill-prog  { background:#dbeafe; color:#1e40af; }
    .pill-warn  { background:#fef9c3; color:#854d0e; }
    .pill-empty { background:#f1f5f9; color:#94a3b8; }
    .pbar-track { height:5px; border-radius:3px; background:#f1f5f9; margin:8px 0 4px; }
    .pbar-fill  { height:5px; border-radius:3px;
                  background:linear-gradient(90deg,#6366f1,#10b981); }
    .alert { border-left:4px solid; border-radius:0 8px 8px 0;
             padding:9px 13px; margin-bottom:7px; font-size:12px; }
    .alert-red   { border-color:#ef4444; background:#fef2f2; color:#7f1d1d; }
    .alert-amber { border-color:#f59e0b; background:#fffbeb; color:#78350f; }
    .alert-blue  { border-color:#3b82f6; background:#eff6ff; color:#1e3a5f; }
    .dl-row { display:flex; justify-content:space-between; align-items:center;
              padding:8px 0; border-bottom:1px solid #f1f5f9; font-size:13px; }
    .funnel-col { text-align:center; padding:12px 8px;
                  border-radius:10px; margin:0 3px; }
    </style>""", unsafe_allow_html=True)

    # ── Header ────────────────────────────────────────────────────────────
    hc1, hc2 = st.columns([4, 1])
    hc1.markdown("## BMS Estimator")
    hc1.caption(today.strftime('%B %d, %Y'))
    if hc2.button("＋ New project", type="primary",
                  use_container_width=True, key="ov_new"):
        st.session_state.nav = "Projects"
        st.session_state.active_project = None
        st.rerun()

    # ── Compute stats ─────────────────────────────────────────────────────
    n = len(projects)

    # Pipeline value
    pipeline_val = 0
    for p in projects.values():
        try:
            lines  = p["estimate"].get("lines", [])
            markup = p["estimate"].get("markup", 10)
            sub    = sum(float(r.get("Total $", 0)) for r in lines)
            pipeline_val += sub * (1 + markup / 100)
        except: pass

    # Due this month
    due_month = 0
    for p in projects.values():
        bd = p.get("bid_date")
        if bd:
            try:
                days = (date.fromisoformat(str(bd)) - today).days
                if 0 <= days <= 30: due_month += 1
            except: pass

    # Proposals ready
    prop_ready = sum(1 for p in projects.values()
                     if module_status(p, "Proposal") == "done")

    # Needs action
    needs_action = 0
    for p in projects.values():
        disc = len(p["takeoff"].get("discrepancies", []))
        if disc: needs_action += 1
        bd = p.get("bid_date")
        if bd:
            try:
                days = (date.fromisoformat(str(bd)) - today).days
                if days <= 30 and module_status(p, "Estimate") == "not_started":
                    needs_action += 1
            except: pass

    # Pipeline funnel counts
    funnel = {"Scoping": 0, "Estimating": 0, "Proposal": 0, "Submitted": 0}
    for p in projects.values():
        ps = module_status(p, "Proposal")
        es = module_status(p, "Estimate")
        pl = module_status(p, "Point List")
        tk = module_status(p, "Takeoff")
        if ps == "done":                          funnel["Submitted"] += 1
        elif es in ("done","in_progress"):        funnel["Proposal"]  += 1
        elif pl in ("done","in_progress"):        funnel["Estimating"]+= 1
        else:                                     funnel["Scoping"]   += 1

    # ── KPI cards ─────────────────────────────────────────────────────────
    k1,k2,k3,k4,k5 = st.columns(5)
    kpi_data = [
        (k1, "📁", str(n),
         "Active bids",
         f"{funnel['Submitted']} submitted" if n else "no projects yet"),
        (k2, "💰",
         f"${pipeline_val/1000:.0f}K" if pipeline_val >= 1000
         else f"${pipeline_val:,.0f}" if pipeline_val else "—",
         "Pipeline value",
         f"{sum(1 for p in projects.values() if p['estimate'].get('lines'))} estimates built"),
        (k3, "📅", str(due_month),
         "Due this month",
         "bids in next 30 days"),
        (k4, "✅", str(prop_ready),
         "Proposals ready",
         f"of {n} active bids"),
        (k5, "⚠️", str(needs_action),
         "Needs action",
         "discrepancies or overdue steps"),
    ]
    for col, icon, val, label, sub in kpi_data:
        color = "#dc2626" if (label == "Needs action" and int(val or 0) > 0) else                 "#d97706" if (label == "Due this month" and int(val or 0) > 0) else                 "#1e293b"
        col.markdown(f"""
        <div class="kpi">
            <div class="kpi-icon">{icon}</div>
            <div class="kpi-val" style="color:{color}">{val}</div>
            <div class="kpi-label">{label}</div>
            <div class="kpi-sub">{sub}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Pipeline funnel ────────────────────────────────────────────────────
    if projects:
        st.markdown("**Bid pipeline**")
        fc = st.columns(4)
        funnel_colors = [
            ("#6366f1","#ede9fe"),
            ("#3b82f6","#dbeafe"),
            ("#10b981","#d1fae5"),
            ("#f59e0b","#fef9c3"),
        ]
        for i,(stage,cnt) in enumerate(funnel.items()):
            col, (fg,bg) = fc[i], funnel_colors[i]
            pct = f"{int(cnt/n*100)}%" if n else "0%"
            col.markdown(f"""
            <div class="funnel-col" style="background:{bg}">
                <div style="font-size:11px;font-weight:600;color:{fg};
                            text-transform:uppercase;letter-spacing:.05em">{stage}</div>
                <div style="font-size:2rem;font-weight:700;color:{fg};
                            line-height:1.2;margin:4px 0">{cnt}</div>
                <div style="font-size:11px;color:{fg};opacity:.7">{pct} of bids</div>
            </div>""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    # ── Main + right panel ────────────────────────────────────────────────
    col_main, col_right = st.columns([1.7, 1])

    with col_main:
        st.markdown("**Projects**")
        if not projects:
            st.markdown("""
            <div style="border:2px dashed #e2e8f0;border-radius:12px;
                        padding:48px;text-align:center">
                <div style="font-size:36px;margin-bottom:12px">📋</div>
                <div style="font-size:16px;font-weight:600;color:#475569;
                            margin-bottom:6px">No projects yet</div>
                <div style="font-size:13px;color:#94a3b8">
                    Click <strong>＋ New project</strong> above to get started</div>
            </div>""", unsafe_allow_html=True)
        else:
            for pname, p in projects.items():
                disc  = len(p["takeoff"].get("discrepancies", []))
                devs  = len(p["takeoff"].get("equipment", []))
                bd    = p.get("bid_date", "")
                cli   = p.get("client") or "—"

                # Progress
                done_n = sum(1 for m in MODULE_ORDER
                             if module_status(p,m) in ("done","in_progress"))
                pct    = int(done_n / len(MODULE_ORDER) * 100)

                # Deadline badge
                dl_html = ""
                if bd:
                    try:
                        days = (date.fromisoformat(str(bd)) - today).days
                        if days < 0:
                            dl_html = f'<span style="color:#94a3b8">Past due</span>'
                        elif days <= 14:
                            dl_html = f'<span style="color:#dc2626;font-weight:600">🔴 {days}d</span>'
                        elif days <= 30:
                            dl_html = f'<span style="color:#d97706;font-weight:600">🟡 {days}d</span>'
                        else:
                            dl_html = f'<span style="color:#16a34a">🟢 {days}d</span>'
                    except:
                        dl_html = f"📅 {bd}"

                # Stage pills
                pills = ""
                for mod in MODULE_ORDER:
                    s = module_status(p, mod)
                    if s == "done":
                        pills += f'<span class="pill pill-done">✓ {mod}</span>'
                    elif s == "in_progress":
                        pills += f'<span class="pill pill-prog">{mod}</span>'
                    elif mod == "Takeoff" and disc:
                        pills += f'<span class="pill pill-warn">⚠ {disc} disc.</span>'
                    else:
                        pills += f'<span class="pill pill-empty">{mod}</span>'

                st.markdown(f"""
                <div class="pcard">
                    <div style="display:flex;justify-content:space-between;align-items:start">
                        <div>
                            <div class="pcard-name">{pname}</div>
                            <div class="pcard-meta">
                                {cli}
                                {"&nbsp;·&nbsp;" + str(devs) + " devices" if devs else ""}
                                {"&nbsp;·&nbsp;" + dl_html if dl_html else ""}
                            </div>
                        </div>
                    </div>
                    <div style="margin-bottom:8px">{pills}</div>
                    <div class="pbar-track">
                        <div class="pbar-fill" style="width:{pct}%"></div>
                    </div>
                    <div style="font-size:11px;color:#94a3b8">
                        {done_n}/{len(MODULE_ORDER)} modules complete
                    </div>
                </div>""", unsafe_allow_html=True)

                if st.button(f"Open {pname} →", key=f"ov_op_{pname}",
                             use_container_width=True):
                    st.session_state.active_project = pname
                    st.session_state.active_module  = "Takeoff"
                    st.session_state.nav            = "Projects"
                    st.rerun()

    with col_right:
        # ── Upcoming deadlines ────────────────────────────────────────────
        st.markdown("**Upcoming deadlines**")
        dls = []
        for pname,p in projects.items():
            bd = p.get("bid_date")
            if bd:
                try:
                    days = (date.fromisoformat(str(bd)) - today).days
                    dls.append((days, pname, bd))
                except: pass
        dls.sort()

        if not dls:
            st.caption("No deadlines set.")
        else:
            for days, pname, bd in dls[:7]:
                if days < 0:
                    color, txt = "#94a3b8", "Past due"
                elif days <= 14:
                    color, txt = "#dc2626", f"{days} days"
                elif days <= 30:
                    color, txt = "#d97706", f"{days} days"
                else:
                    color, txt = "#16a34a", f"{days} days"
                st.markdown(f"""
                <div class="dl-row">
                    <span style="font-weight:500">{pname}</span>
                    <span style="color:{color};font-weight:600;font-size:12px">{txt}</span>
                </div>""", unsafe_allow_html=True)

        # ── Alerts ────────────────────────────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("**Needs attention**")
        alerts = []
        for pname,p in projects.items():
            disc = p["takeoff"].get("discrepancies",[])
            if disc:
                alerts.append(("red",
                    f"<b>{pname}</b> — {len(disc)} discrepancies need scope clarification"))
            bd = p.get("bid_date")
            if bd:
                try:
                    days = (date.fromisoformat(str(bd)) - today).days
                    if days <= 30 and module_status(p,"Estimate") == "not_started":
                        alerts.append(("amber",
                            f"<b>{pname}</b> — no estimate, {days}d to bid"))
                    if days <= 14 and module_status(p,"Proposal") == "not_started":
                        alerts.append(("red",
                            f"<b>{pname}</b> — no proposal, {days}d to bid"))
                except: pass
            if (p["docs"].get("SOO") and
                module_status(p,"Point List") == "not_started"):
                alerts.append(("blue",
                    f"<b>{pname}</b> — SOO uploaded, point list not generated"))

        if not alerts:
            st.markdown("""
            <div style="background:#f0fdf4;border:1px solid #bbf7d0;
                        border-radius:8px;padding:14px;text-align:center;
                        color:#166534;font-size:13px">
                ✅ All clear — no issues
            </div>""", unsafe_allow_html=True)
        else:
            for color, msg in alerts[:6]:
                css = {"red":"alert-red","amber":"alert-amber",
                       "blue":"alert-blue"}.get(color,"alert-blue")
                st.markdown(
                    f'<div class="alert {css}">{msg}</div>',
                    unsafe_allow_html=True)

        # ── Summary stats ─────────────────────────────────────────────────
        if projects:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("**Summary**")
            total_dev  = sum(len(p["takeoff"].get("equipment",[]))
                             for p in projects.values())
            total_disc = sum(len(p["takeoff"].get("discrepancies",[]))
                             for p in projects.values())
            for label, val in [
                ("Total devices in scope", total_dev),
                ("Total discrepancies",    total_disc),
                ("Proposals submitted",    prop_ready),
                ("Pipeline value",
                 f"${pipeline_val/1000:.0f}K" if pipeline_val else "—"),
            ]:
                sc1,sc2 = st.columns([2,1])
                sc1.caption(label)
                sc2.markdown(f"**{val}**")

    # ── Roadmap panel ─────────────────────────────────────────────────────
    st.divider()
    with st.expander("🗺 Product status & roadmap"):
        _product_status_panel()
# ── Clients ───────────────────────────────────────────────────────────────────
def page_clients():
    st.title("Clients")
    st.caption("Save each client's point list template (Excel), proposal template (Word), "
               "and labor rates. Select a client when creating a project to auto-apply their formats.")

    clients = st.session_state.clients
    col_list, col_form = st.columns([1,1.6])

    with col_list:
        st.markdown("**Saved clients**")
        if not clients:
            st.info("No clients yet.")
        for cname in list(clients.keys()):
            c = clients[cname]
            with st.expander(f"**{cname}**"):
                st.caption(f"Point list template: `{c.get('pl_template_name','—')}`")
                st.caption(f"Proposal template: `{c.get('prop_template_name','—')}`")
                rates = c.get("rates", DEFAULT_RATES)
                st.caption("Rates: " + "  ·  ".join(f"{k}: **${v}/hr**" for k,v in rates.items()))
                projs_using = [pname for pname,p in st.session_state.projects.items()
                               if p.get("client")==cname]
                if projs_using:
                    st.caption(f"Used by: {', '.join(projs_using)}")
                if st.button("Delete", key=f"del_{cname}"):
                    del st.session_state.clients[cname]
                    st.rerun()

    with col_form:
        st.markdown("**Add / update client**")
        with st.form("client_form", clear_on_submit=True):
            cname = st.text_input("Client name *", placeholder="e.g. Johnson Controls NYC")

            st.markdown("**Point list template** — upload your Excel format")
            pl_file = st.file_uploader("Excel (.xlsx)", type=["xlsx"], key="pl_up")
            st.caption("AI will read your column headers and output the point list in exactly this format.")

            st.markdown("**Proposal template** — upload your Word format")
            prop_file = st.file_uploader("Word (.docx)", type=["docx"], key="prop_up")
            st.caption("Use {{PROJECT_NAME}}, {{CLIENT}}, {{DATE}}, {{SCOPE_TEXT}} as placeholders in your template.")

            st.markdown("**Labor rates ($/hr)**")
            rc = st.columns(len(PHASES))
            rates = {}
            for i,ph in enumerate(PHASES):
                rates[ph] = rc[i].number_input(ph, 0, 500, DEFAULT_RATES[ph], key=f"r_{ph}")

            if st.form_submit_button("Save client", type="primary"):
                if not cname:
                    st.error("Client name required.")
                else:
                    entry = {"rates":rates}
                    if pl_file:
                        entry["pl_template_bytes"] = pl_file.read()
                        entry["pl_template_name"]  = pl_file.name
                    if prop_file:
                        entry["prop_template_bytes"] = prop_file.read()
                        entry["prop_template_name"]  = prop_file.name
                    st.session_state.clients[cname] = entry
                    _save_app_state()
                    st.success(f"✅ '{cname}' saved.")
                    st.rerun()

# ── Projects hub ──────────────────────────────────────────────────────────────
def page_projects():
    active = st.session_state.active_project
    if active and active in st.session_state.projects:
        page_project_detail(st.session_state.projects[active])
    else:
        page_projects_list()

def page_projects_list():
    st.title("Projects")
    projects = st.session_state.projects

    with st.expander("➕ New project", expanded=not bool(projects)):
        with st.form("new_proj"):
            # ── Basic info ────────────────────────────────────────────
            st.markdown("**Project details**")
            c1,c2 = st.columns(2)
            pname    = c1.text_input("Project name *")
            address  = c2.text_input("Address")
            c3,c4   = st.columns(2)
            bid_date = c3.date_input("Bid date", value=None)
            # Saved client templates (for reuse)
            saved_names = list(st.session_state.clients.keys())
            client_opts = ["New client / no template"] + saved_names
            client_sel  = c4.selectbox("Reuse saved settings", client_opts,
                                        help="Pick a previously saved client to auto-fill rates and templates")

            st.divider()

            # ── Templates ─────────────────────────────────────────────
            st.markdown("**Templates** *(optional — skip if not needed)*")
            t1,t2 = st.columns(2)
            pl_file   = t1.file_uploader("Point list template (.xlsx)",
                                          type=["xlsx"], key="np_pl")
            prop_file = t2.file_uploader("Proposal template (.docx)",
                                          type=["docx"], key="np_prop")
            t1.caption("AI matches your column format exactly")
            t2.caption("Use {{PROJECT_NAME}} {{CLIENT}} {{DATE}} {{SCOPE_TEXT}}")

            st.divider()

            # ── Labor rates ───────────────────────────────────────────
            st.markdown("**Labor rates ($/hr)**")
            # Pre-fill from saved client if selected
            saved_rates = (st.session_state.clients.get(client_sel, {}).get("rates", DEFAULT_RATES)
                           if client_sel != "New client / no template" else DEFAULT_RATES)
            rc = st.columns(len(PHASES))
            rates = {}
            for i,ph in enumerate(PHASES):
                rates[ph] = rc[i].number_input(ph, 0, 500,
                                                int(saved_rates.get(ph, DEFAULT_RATES[ph])),
                                                key=f"np_rate_{ph}")

            st.divider()

            # ── Documents ─────────────────────────────────────────────
            st.markdown("**Project documents** *(upload now or later in Takeoff tab)*")
            d1,d2,d3 = st.columns(3)
            draw_f = d1.file_uploader("Drawings (PDF)",   type=["pdf"],        key="np_draw")
            soo_f  = d2.file_uploader("SOO (PDF/DOCX)",   type=["pdf","docx"], key="np_soo")
            spec_f = d3.file_uploader("Controls spec",    type=["pdf","docx"], key="np_spec")

            if st.form_submit_button("Create project", type="primary"):
                if not pname:
                    st.error("Project name required.")
                elif pname in projects:
                    st.error("A project with this name already exists.")
                else:
                    # Use saved client name as label if reusing
                    client_label = (client_sel
                                    if client_sel != "New client / no template"
                                    else None)
                    p = new_project(pname, client_label,
                                    str(bid_date) if bid_date else None, address)

                    # Attach documents
                    for label,f in [("Drawings",draw_f),("SOO",soo_f),
                                    ("Controls spec",spec_f)]:
                        if f:
                            p["docs"][label]      = f.read()
                            p["doc_names"][label] = f.name

                    # Set rates
                    p["estimate"]["rates"] = dict(rates)

                    # Save templates into clients store for reuse
                    if pl_file or prop_file:
                        entry = {"rates": rates}
                        if pl_file:
                            entry["pl_template_bytes"] = pl_file.read()
                            entry["pl_template_name"]  = pl_file.name
                        if prop_file:
                            entry["prop_template_bytes"] = prop_file.read()
                            entry["prop_template_name"]  = prop_file.name
                        # Save under project name so it can be reused
                        key = client_label or pname
                        st.session_state.clients[key] = entry
                    elif client_label:
                        # Inherit templates from saved client
                        saved_cl = st.session_state.clients.get(client_label, {})
                        if saved_cl:
                            p["_inherited_client"] = client_label

                    st.session_state.projects[pname] = p
                    st.session_state.active_project  = pname
                    st.session_state.active_module   = "Takeoff"
                    _save_app_state()
                    st.success(f"✅ '{pname}' created.")
                    st.rerun()

    # Edit state
    if "editing_project" not in st.session_state:
        st.session_state.editing_project = None

    for pname,p in list(projects.items()):
        disc = len(p["takeoff"].get("discrepancies",[]))
        devs = len(p["takeoff"].get("equipment",[]))
        with st.container(border=True):

            # ── Editing mode ──────────────────────────────────────────
            if st.session_state.editing_project == pname:
                st.markdown(f"**Editing: {pname}**")
                with st.form(f"edit_proj_{pname}"):
                    ec1,ec2 = st.columns(2)
                    new_name    = ec1.text_input("Project name", value=pname)
                    new_address = ec2.text_input("Address", value=p.get("address",""))
                    ec3,ec4 = st.columns(2)
                    client_opts = ["(no client)"] + list(st.session_state.clients.keys())
                    cur_client  = p.get("client") or "(no client)"
                    new_client  = ec3.selectbox("Client", client_opts,
                                                index=client_opts.index(cur_client)
                                                if cur_client in client_opts else 0)
                    cur_bid = None
                    try:
                        from datetime import date as _date
                        cur_bid = _date.fromisoformat(str(p.get("bid_date",""))) if p.get("bid_date") else None
                    except Exception:
                        pass
                    new_bid = ec4.date_input("Bid date", value=cur_bid)
                    sc1,sc2 = st.columns(2)
                    if sc1.form_submit_button("Save changes", type="primary"):
                        if new_name and new_name != pname:
                            projects[new_name] = projects.pop(pname)
                            pname = new_name
                            p = projects[pname]
                        p["address"]  = new_address
                        p["client"]   = new_client if new_client != "(no client)" else None
                        p["bid_date"] = str(new_bid) if new_bid else None
                        if new_client and new_client != "(no client)":
                            cl = st.session_state.clients.get(new_client,{})
                            if cl.get("rates"):
                                p["estimate"]["rates"] = dict(cl["rates"])
                        st.session_state.editing_project = None
                        _save_app_state()
                        st.rerun()
                    if sc2.form_submit_button("Cancel"):
                        st.session_state.editing_project = None
                        st.rerun()

            # ── Normal view ───────────────────────────────────────────
            else:
                r1,r2,r3 = st.columns([3,4,2])
                r1.markdown(f"### {pname}")
                r1.caption(f"{p.get('address','—')} · Client: {p.get('client','—')}")
                r1.caption(f"Bid: {p.get('bid_date','TBD')} · {devs} devices")
                html = ""
                for mod in MODULE_ORDER:
                    s = module_status(p,mod)
                    lbl = (f"⚠️{disc}" if mod=="Takeoff" and disc else
                           ("Done" if s=="done" else ("In progress" if s=="in_progress" else "—")))
                    html += chip("issues" if mod=="Takeoff" and disc else s, f"{mod}: {lbl}") + " "
                r2.markdown(html, unsafe_allow_html=True)
                rb1,rb2,rb3 = r3.columns(3)
                if rb1.button("Open", key=f"op_{pname}", type="primary"):
                    st.session_state.active_project = pname
                    st.session_state.active_module  = "Takeoff"
                    st.rerun()
                if rb2.button("✏️", key=f"ed_{pname}", help="Edit project details"):
                    st.session_state.editing_project = pname
                    st.rerun()
                if rb3.button("🗑", key=f"dl_{pname}", help="Delete project"):
                    st.session_state[f"confirm_delete_{pname}"] = True
                    st.rerun()

                # Confirm delete
                if st.session_state.get(f"confirm_delete_{pname}"):
                    st.warning(f"Delete **{pname}**? This cannot be undone.")
                    cc1,cc2 = st.columns(2)
                    if cc1.button("Yes, delete", key=f"yes_del_{pname}", type="primary"):
                        del projects[pname]
                        st.session_state.pop(f"confirm_delete_{pname}", None)
                        if st.session_state.active_project == pname:
                            st.session_state.active_project = None
                        _save_app_state()
                        st.rerun()
                    if cc2.button("Cancel", key=f"no_del_{pname}"):
                        st.session_state.pop(f"confirm_delete_{pname}", None)
                        st.rerun()

def page_project_detail(p):
    bc, hc = st.columns([1, 8])
    if bc.button("← Back"):
        st.session_state.active_project = None
        st.rerun()
    hc.markdown(f"## {p['name']}")
    hc.caption(
        f"{p.get('address','—')} · "
        f"Bid: {p.get('bid_date','TBD')}"
        + (f" · Client: {p.get('client')}" if p.get('client') else "")
    )

    # All modules in order
    all_mods = MODULE_ORDER + ["AI Advisor", "Drawing Markup"]

    # Build tab labels
    tab_labels = []
    for mod in all_mods:
        if mod == "AI Advisor":
            tab_labels.append("🤖 AI Advisor")
        elif mod == "Drawing Markup":
            tab_labels.append("🖊 Drawing Markup")
        elif module_locked(p, mod):
            tab_labels.append(f"🔒 {mod}")
        else:
            s    = module_status(p, mod)
            icon = "✅" if s == "done" else "⚠️" if s == "issues" else "📋"
            tab_labels.append(f"{icon} {mod}")

    # Determine which tab to show based on sidebar click
    active_mod = st.session_state.get("active_module", "Takeoff")
    try:
        default_tab = all_mods.index(active_mod)
    except ValueError:
        default_tab = 0

    tabs = st.tabs(tab_labels)
    handlers = [module_takeoff, module_point_list, module_estimate,
                module_proposal, module_ai_advisor, module_markup]

    for i, (tab, mod, handler) in enumerate(zip(tabs, all_mods, handlers)):
        with tab:
            if mod not in ("AI Advisor", "Drawing Markup") and module_locked(p, mod):
                unlock_msg = {
                    "Point List": "Upload SOO or Controls spec in the Takeoff tab to unlock.",
                    "Estimate":   "Generate a point list or upload Controls spec to unlock.",
                    "Proposal":   "Generate an estimate or complete takeoff to unlock.",
                }.get(mod, "Complete previous steps to unlock.")
                st.info(f"🔒 **{mod} is locked.** {unlock_msg}")
            else:
                warn = module_data_warning(p, mod)
                if warn and mod not in ("AI Advisor", "Drawing Markup", "Takeoff"):
                    st.warning(warn)
                handler(p)

# ── Module 1: Takeoff ─────────────────────────────────────────────────────────
def module_takeoff(p):
    st.markdown("### Takeoff")
    docs = p.get("doc_names",{})

    c1,c2,c3 = st.columns(3)
    c1.info(f"📐 Drawings: `{docs.get('Drawings','not uploaded')}`")
    c2.info(f"📄 SOO: `{docs.get('SOO','not uploaded')}`")
    c3.info(f"📋 Spec: `{docs.get('Controls spec','—')}`")

    with st.expander("Add / replace documents"):
        f1,f2,f3 = st.columns(3)
        nd = f1.file_uploader("Drawings",     type=["pdf"],        key="tk_d")
        ns = f2.file_uploader("SOO",          type=["pdf","docx"], key="tk_s")
        nc = f3.file_uploader("Controls spec",type=["pdf","docx"], key="tk_c")
        if st.button("Save", key="tk_save"):
            for lbl,f in [("Drawings",nd),("SOO",ns),("Controls spec",nc)]:
                if f:
                    p["docs"][lbl]=f.read(); p["doc_names"][lbl]=f.name
            st.success("Saved."); st.rerun()

    st.divider()

    # ── Load takeoff data ─────────────────────────────────────────────────
    st.markdown("**Extract device tags from drawings**")
    st.caption(
        "Searches the drawing PDF text layer for BMS device tags. "
        "No API key needed — works entirely offline using PyMuPDF. "
        "Cross-checks against SOO automatically."
    )

    if not p["docs"].get("Drawings"):
        st.warning("⚠️ Upload drawings using **Add / replace documents** above first.")
    else:
        fname = p["doc_names"].get("Drawings", "")
        fsize = round(len(p["docs"]["Drawings"]) / 1024 / 1024, 1)
        c1, c2 = st.columns([2, 1])
        c1.info(f"📐 `{fname}` · {fsize} MB ready")
        if c2.button("🔍 Run takeoff", type="primary", key="run_tk"):
            prog = st.progress(0, text="Opening PDF...")
            try:
                prog.progress(15, text="Reading text layer — scanning every page...")
                pdf_bytes = p["docs"]["Drawings"]
                prog.progress(40, text="Finding device tags (FCU, AHU, DOAS, EUH, UH...)...")
                result = run_pdf_takeoff(pdf_bytes)
                prog.progress(85, text="Cross-checking against SOO...")
                takeoff = takeoff_to_session_format(result)
                prog.progress(100, text="Done.")
                p["takeoff"].update(takeoff)
                _save_app_state()
                stats = result["stats"]
                st.success(
                    f"✅ {stats['total_pages']} pages read · "
                    f"{stats['schedule_pages']} schedule pages · "
                    f"**{stats['total_tags']} devices found** · "
                    f"**{stats['discrepancies']} discrepancies**"
                )
                st.rerun()
            except Exception as e:
                prog.progress(100, text="Error.")
                st.error(f"Error reading PDF: {e}")

    st.divider()
    with st.expander("Or load from JSON (pre-processed data)"):
        st.caption("Upload schedule_ground_truth.json if you have pre-processed data.")
        gt = st.file_uploader("schedule_ground_truth.json", type=["json"], key="tk_gt")
        if gt:
            if st.button("Load JSON", key="tk_load", type="primary"):
                data = json.load(gt)
                equip = data.get("equipment", [])
                p["takeoff"]["equipment"]     = equip
                p["takeoff"]["discrepancies"] = [e for e in equip if e.get("discrepancy_flag")]
                p["takeoff"]["status"]        = "issues" if p["takeoff"]["discrepancies"] else "done"
                _save_app_state()
                st.success(f"✅ {len(equip)} devices · {len(p['takeoff']['discrepancies'])} discrepancies")
                st.rerun()

    equip = p["takeoff"].get("equipment",[])
    discs = p["takeoff"].get("discrepancies",[])
    if not equip:
        st.info("No takeoff data. Upload drawings and click **Run takeoff** above.")
        return

    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Total devices",  len(equip))
    m2.metric("SOO confirmed",  sum(1 for e in equip if e.get("soo_confirmed")))
    m3.metric("Discrepancies",  len(discs), delta=f"{len(discs)} issues" if discs else None,
              delta_color="inverse" if discs else "normal")
    m4.metric("Needs review",   sum(1 for e in equip if e.get("soo_confirmed") is None and not e.get("discrepancy_flag")))

    if discs:
        st.markdown(
            f'<div class="disc-banner">⚠️ <strong>{len(discs)} devices have no SOO sequence.</strong> '
            f'Review below — use AI Advisor to resolve.</div>', unsafe_allow_html=True)

    t1,t2,t3 = st.tabs(["Discrepancies","All devices","By classification"])
    with t1:
        if not discs: st.success("No discrepancies.")
        else:
            df = pd.DataFrame([{"Tag":d.get("tag",""),"System":d.get("system",""),
                                 "Floor":d.get("floor",""),"Severity":"HIGH",
                                 "Action":d.get("action","Verify BMS scope")} for d in discs])
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button("⬇ Export CSV", df.to_csv(index=False),
                               f"discrepancies_{p['name'].replace(' ','_')}.csv")
    with t2:
        rows = [{"Tag":e.get("tag",""),"Floor":e.get("floor",""),"System":e.get("system",""),
                 "Classification":e.get("classification",""),
                 "BMS":e.get("bms_interface_default",e.get("bms_interface","")),
                 "Status":get_status(e)} for e in equip]
        df2 = pd.DataFrame(rows)
        srch = st.text_input("Search", placeholder="FCU, pump, AHU…", key="tk_srch")
        if srch:
            df2 = df2[df2["Tag"].str.contains(srch,case=False,na=False)|
                      df2["System"].str.contains(srch,case=False,na=False)]
        st.dataframe(df2, use_container_width=True, hide_index=True, height=400)
        st.download_button("⬇ Export CSV", df2.to_csv(index=False),
                           f"register_{p['name'].replace(' ','_')}.csv")
    with t3:
        agg = defaultdict(lambda:{"Total":0,"Confirmed":0,"Discrepancy":0})
        for e in equip:
            cls = e.get("classification","Unknown")
            agg[cls]["Total"] += 1
            s = get_status(e)
            if s=="SOO confirmed": agg[cls]["Confirmed"]+=1
            elif s=="Discrepancy": agg[cls]["Discrepancy"]+=1
        df3 = pd.DataFrame([{"Classification":k,"Total":v["Total"],
                              "Confirmed":v["Confirmed"],"Discrepancies":v["Discrepancy"]}
                             for k,v in sorted(agg.items())])
        st.bar_chart(df3.set_index("Classification")[["Confirmed","Discrepancies"]],
                     color=["#22c55e","#f59e0b"])
        st.dataframe(df3, use_container_width=True, hide_index=True)

# ── Module 2: Point List ──────────────────────────────────────────────────────
def module_point_list(p):
    st.markdown("### Point list")
    client  = p.get("client")
    cl      = st.session_state.clients.get(client,{}) if client else {}
    pl_tmpl = cl.get("pl_template_bytes")
    pl_name = cl.get("pl_template_name","")

    if pl_tmpl:
        st.success(f"✅ Client template loaded: `{pl_name}` — AI will match your column format exactly.")
    else:
        st.info("No client template. AI uses standard columns. Add a template in the Clients tab.")

    has_takeoff = len(p["takeoff"].get("equipment", [])) > 0
    has_soo     = bool(p["docs"].get("SOO"))
    has_spec    = bool(p["docs"].get("Controls spec"))

    if not has_takeoff:
        st.info("ℹ️ No takeoff loaded — point list will be generated from SOO/spec. "
                "Exact device tags will not be available until takeoff is done.")
    if not has_soo and not has_spec:
        st.warning("⚠️ Upload SOO or Controls spec in the Takeoff tab for best results.")

    # ── Diagnostics ───────────────────────────────────────────────────────
    with st.expander("🔍 Diagnostics — click to check if SOO is loaded"):
        soo_bytes  = p["docs"].get("SOO")
        spec_bytes = p["docs"].get("Controls spec")
        k_check    = api_key()
        st.write({
            "SOO uploaded":          bool(soo_bytes),
            "SOO size (KB)":         round(len(soo_bytes)/1024, 1) if soo_bytes else 0,
            "Controls spec uploaded": bool(spec_bytes),
            "API key set":           bool(k_check),
            "API key prefix":        k_check[:12] + "..." if k_check else "none",
            "Takeoff devices":       len(p["takeoff"].get("equipment",[])),
            "Client":                p.get("client","none"),
        })
        if soo_bytes:
            # Try extracting first 200 chars
            try:
                import fitz
                doc = fitz.open(stream=soo_bytes, filetype="pdf")
                preview = doc[0].get_text()[:300].strip()
                st.markdown(f"**SOO text preview (page 1):**")
                st.code(preview)
            except Exception as e:
                st.error(f"Could not read SOO: {e}")

    if st.button("🤖 Generate point list", type="primary", key="gen_pl"):
        k = api_key()
        if not k:
            st.error("❌ No API key. Add it in Streamlit dashboard → Settings → Secrets: ANTHROPIC_API_KEY = \"sk-ant-...\"")
        elif not p["docs"].get("SOO") and not p["docs"].get("Controls spec"):
            st.error("❌ No SOO or controls spec found in this project. "
                     "Go to the Takeoff tab → Add/replace documents → upload your SOO PDF.")
        else:
            prog = st.progress(0, text="Reading SOO...")
            try:
                prog.progress(20, text="Extracting text from SOO...")
                # Test extraction first
                soo_b = p["docs"].get("SOO")
                if soo_b:
                    import fitz as _fitz
                    _doc = _fitz.open(stream=soo_b, filetype="pdf")
                    _preview = " ".join(page.get_text() for page in _doc)[:200]
                    prog.progress(40, text=f"SOO text found ({len(_preview)} chars preview)...")
                prog.progress(60, text="Sending to Claude...")
                rows = ai_point_list(p, k, pl_tmpl, pl_name)
                prog.progress(100, text="Done.")
                p["point_list"]["rows"]   = rows
                p["point_list"]["status"] = "done"
                _save_app_state()
                st.success(f"✅ {len(rows)} points generated.")
                st.rerun()
            except Exception as e:
                prog.progress(100, text="Error.")
                st.error(f"Error: {e}")

    rows = p["point_list"].get("rows",[])
    if not rows:
        st.info("No point list yet. Click Generate."); return

    st.markdown(f"**{len(rows)} points** — edit any cell directly:")
    edited = st.data_editor(pd.DataFrame(rows), use_container_width=True,
                            hide_index=True, num_rows="dynamic", key="pl_ed")
    p["point_list"]["rows"] = edited.to_dict("records")

    if st.button("⬇ Export to Excel", key="exp_pl"):
        xb = export_pl_excel(edited, pl_tmpl)
        st.download_button("Download .xlsx", xb,
                           f"point_list_{p['name'].replace(' ','_')}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="dl_pl")

# ── Module 3: Estimate ────────────────────────────────────────────────────────
def module_estimate(p):
    st.markdown("### Estimate")
    init_pricebooks()

    est_tab1, est_tab2, est_tab3 = st.tabs(["⏱ Labor estimate", "🔧 Material estimate", "📊 Combined total"])

    with est_tab1:
        _labor_estimate(p)
    with est_tab2:
        module_material(p)
    with est_tab3:
        _combined_total(p)


def _labor_estimate(p):
    client  = p.get("client")
    cl      = st.session_state.clients.get(client,{}) if client else {}
    saved   = p["estimate"].get("rates") or cl.get("rates") or DEFAULT_RATES

    with st.expander("⚙️ Labor rates ($/hr)"):
        rc = st.columns(len(PHASES))
        rates = {}
        for i,ph in enumerate(PHASES):
            rates[ph] = rc[i].number_input(ph,0,500,int(saved.get(ph,DEFAULT_RATES[ph])),key=f"er_{ph}")
        p["estimate"]["rates"] = rates

    markup = st.slider("Markup %",0,50,int(p["estimate"].get("markup",10)),key="mk_sl")
    p["estimate"]["markup"] = markup

    if st.button("🤖 Generate labor estimate", type="primary", key="gen_est"):
        k = api_key()
        if not k: st.error("Add API key in sidebar.")
        else:
            with st.spinner("Claude is reading SOO, controls spec, and point list to estimate hours..."):
                lines = ai_estimate(p, k, rates, markup)
            p["estimate"]["lines"]  = lines
            p["estimate"]["status"] = "done"
            st.rerun()

    lines = p["estimate"].get("lines",[])
    if not lines:
        st.info("No labor estimate yet. Click Generate."); return

    edited = st.data_editor(pd.DataFrame(lines), use_container_width=True,
                            hide_index=True, num_rows="dynamic", key="est_ed")
    p["estimate"]["lines"] = edited.to_dict("records")

    try:
        sub = sum(float(r.get("Total $",0)) for r in edited.to_dict("records"))
        mk  = sub*markup/100
        t1,t2,t3 = st.columns(3)
        t1.metric("Labor subtotal",    f"${sub:,.0f}")
        t2.metric(f"Markup ({markup}%)",f"${mk:,.0f}")
        t3.metric("Labor total",        f"${sub+mk:,.0f}")
    except: pass

    if st.button("⬇ Export labor to Excel", key="exp_est"):
        out = io.BytesIO()
        edited.to_excel(out, index=False)
        st.download_button("Download .xlsx", out.getvalue(),
                           f"labor_{p['name'].replace(' ','_')}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="dl_est")


def _combined_total(p):
    st.markdown("**Combined estimate summary**")
    markup = p["estimate"].get("markup", 10)

    # Labor
    labor_lines = p["estimate"].get("lines", [])
    try:
        labor_sub = sum(float(r.get("Total $",0)) for r in labor_lines)
        labor_mk  = labor_sub * markup / 100
        labor_tot = labor_sub + labor_mk
    except:
        labor_sub = labor_mk = labor_tot = 0

    # Material
    mat = p.get("material", {})
    mat_items = mat.get("items", [])
    mat_markup = mat.get("markup", markup)
    try:
        mat_sub = sum(i.get("qty",0) * i.get("unit_cost",0) for i in mat_items)
        mat_mk  = mat_sub * mat_markup / 100
        mat_tot = mat_sub + mat_mk
    except:
        mat_sub = mat_mk = mat_tot = 0

    grand = labor_tot + mat_tot

    # Summary table
    rows = [
        {"Category":"Labor","Subtotal":f"${labor_sub:,.0f}",f"Markup ({markup}%)":f"${labor_mk:,.0f}","Total":f"${labor_tot:,.0f}"},
        {"Category":"Material","Subtotal":f"${mat_sub:,.0f}",f"Markup ({mat_markup}%)":f"${mat_mk:,.0f}","Total":f"${mat_tot:,.0f}"},
        {"Category":"GRAND TOTAL","Subtotal":"","f`Markup`:":""," Total":f"${grand:,.0f}"},
    ]

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Labor total",    f"${labor_tot:,.0f}")
    c2.metric("Material total", f"${mat_tot:,.0f}")
    c3.metric("Grand total",    f"${grand:,.0f}")
    c4.metric("Labor items",    len(labor_lines))

    st.divider()
    st.markdown("**Labor breakdown**")
    if labor_lines:
        st.dataframe(pd.DataFrame(labor_lines)[["System","Total hrs","Total $"]]
                     if "System" in pd.DataFrame(labor_lines).columns else pd.DataFrame(labor_lines),
                     use_container_width=True, hide_index=True)

    st.markdown("**Material breakdown by section**")
    if mat_items:
        from collections import defaultdict as _dd
        sec_totals = _dd(float)
        for i in mat_items:
            sec_totals[i.get("section","Other")] += i.get("qty",0)*i.get("unit_cost",0)
        df_sec = pd.DataFrame([{"Section":k,"Total":f"${v:,.2f}"} for k,v in sec_totals.items()])
        st.dataframe(df_sec, use_container_width=True, hide_index=True)

    if grand > 0 and st.button("⬇ Export combined summary to Excel", key="exp_combined"):
        out = _export_combined_excel(p, labor_lines, mat_items, labor_sub, labor_mk,
                                     mat_sub, mat_mk, grand, markup, mat_markup)
        st.download_button("Download .xlsx", out,
                           f"full_estimate_{p['name'].replace(' ','_')}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="dl_combined")


def _export_combined_excel(p, labor_lines, mat_items, labor_sub, labor_mk,
                           mat_sub, mat_mk, grand, labor_markup, mat_markup):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook()

    # Sheet 1: Summary
    ws = wb.active; ws.title = "Summary"
    ws["A1"] = f"Full Estimate — {p['name']}"
    ws["A1"].font = Font(bold=True, size=14, name="Arial")
    fill_blue = PatternFill("solid", start_color="1F4E79")
    for r,(label,val) in enumerate([
        ("Labor subtotal", labor_sub), (f"Labor markup ({labor_markup}%)", labor_mk),
        ("Labor total", labor_sub+labor_mk), ("",""),
        ("Material subtotal", mat_sub), (f"Material markup ({mat_markup}%)", mat_mk),
        ("Material total", mat_sub+mat_mk), ("",""),
        ("GRAND TOTAL", grand),
    ], start=3):
        ws.cell(r,1,label).font = Font(name="Arial", bold=(label in ("GRAND TOTAL","Labor total","Material total")))
        ws.cell(r,2,val if isinstance(val,float) else "").number_format = '$#,##0.00'
        if label == "GRAND TOTAL":
            ws.cell(r,1).font = Font(bold=True,color="FFFFFF",name="Arial")
            ws.cell(r,1).fill = fill_blue
            ws.cell(r,2).font = Font(bold=True,color="FFFFFF",name="Arial")
            ws.cell(r,2).fill = fill_blue

    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 16

    # Sheet 2: Labor
    if labor_lines:
        ws2 = wb.create_sheet("Labor Estimate")
        df_l = pd.DataFrame(labor_lines)
        ws2.append(list(df_l.columns))
        for row in df_l.values.tolist():
            ws2.append([str(v) if v is not None else "" for v in row])

    # Sheet 3: Material
    if mat_items:
        ws3 = wb.create_sheet("Material Estimate")
        cols = ["section","subsection","description","manufacturer","part_no","qty","unit_cost","ext_cost"]
        ws3.append([c.replace("_"," ").title() for c in cols])
        for item in mat_items:
            ws3.append([item.get(c,"") for c in cols])

    out = io.BytesIO(); wb.save(out); return out.getvalue()

# ── Module 4: Proposal ────────────────────────────────────────────────────────
def module_proposal(p):
    st.markdown("### Proposal")
    client    = p.get("client")
    cl        = st.session_state.clients.get(client,{}) if client else {}
    prop_tmpl = cl.get("prop_template_bytes")
    prop_name = cl.get("prop_template_name","")

    if prop_tmpl:
        st.success(f"✅ Client template: `{prop_name}` — placeholders: {{{{PROJECT_NAME}}}}, {{{{CLIENT}}}}, {{{{DATE}}}}, {{{{SCOPE_TEXT}}}}")
    else:
        st.info("No proposal template — AI writes a standard TEC-style proposal. Add your Word template in the Clients tab.")

    # Show what data is available
    has_takeoff  = len(p["takeoff"].get("equipment",[])) > 0
    has_estimate = len(p["estimate"].get("lines",[])) > 0
    has_soo      = bool(p["docs"].get("SOO"))
    has_pl       = len(p["point_list"].get("rows",[])) > 0

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Devices",    len(p["takeoff"].get("equipment",[])))
    c2.metric("Points",     len(p["point_list"].get("rows",[])))
    c3.metric("Est. lines", len(p["estimate"].get("lines",[])))
    c4.metric("SOO",        "✅" if has_soo else "—")

    if not has_takeoff and not has_soo:
        st.warning("⚠️ Upload SOO or complete takeoff for a meaningful proposal.")

    if st.button("🤖 Generate proposal", type="primary", key="gen_prop"):
        k = api_key()
        if not k:
            st.error("❌ No API key. Add ANTHROPIC_API_KEY in Streamlit Secrets.")
        else:
            prog = st.progress(0, text="Building scope from project data...")
            try:
                prog.progress(30, text="Sending to Claude...")
                text = ai_proposal(p, k)
                prog.progress(100, text="Done.")
                if not text:
                    st.error("Claude returned empty response. Check your API key in Streamlit Secrets.")
                else:
                    p["proposal"]["text"]   = text
                    p["proposal"]["status"] = "done"
                    _save_app_state()
                    st.success("✅ Proposal generated.")
                    st.rerun()
            except Exception as e:
                prog.progress(100, text="Error.")
                st.error(f"Error: {e}")

    text = p["proposal"].get("text","")
    if not text:
        st.info("No proposal yet. Click Generate above.")
        return

    edited = st.text_area("Proposal text — edit before exporting", value=text,
                          height=520, key="prop_ed")
    p["proposal"]["text"] = edited

    if st.button("⬇ Export to Word (.docx)", key="exp_prop"):
        db = export_prop_docx(edited, p, prop_tmpl)
        st.download_button("Download .docx", db,
                           f"proposal_{p['name'].replace(' ','_')}.docx",
                           "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                           key="dl_prop")

# ── Module 5: AI Advisor ──────────────────────────────────────────────────────
def module_ai_advisor(p):
    st.markdown("### AI Advisor")
    st.caption("Ask anything about this project. Claude has full context of all uploaded documents and module outputs.")
    k = api_key()
    if not k:
        st.error("Add your Anthropic API key in the sidebar."); return

    equip = p["takeoff"].get("equipment",[])
    discs = p["takeoff"].get("discrepancies",[])
    tags  = sorted(set(e.get("tag","") for e in equip if e.get("tag")))

    # Quick action buttons
    st.markdown("**Quick actions**")
    qa1,qa2,qa3 = st.columns(3)
    if discs and qa1.button(f"Resolve {len(discs)} discrepancies ↗", key="qa1"):
        _ask(f"I have {len(discs)} discrepancies in {p['name']}: "
             f"{', '.join(d.get('tag','') for d in discs[:12])}. "
             f"For each tag, what BMS scope is typically required and what should I confirm with the engineer?",
             p, k)
    if qa2.button("Review estimate ↗", key="qa2"):
        n = len(p["estimate"].get("lines",[]))
        _ask(f"Review the {n}-line estimate for {p['name']}. "
             f"Are there any line items that seem off vs industry norms? What might be missing?", p, k)
    if qa3.button("Scope gap check ↗", key="qa3"):
        _ask(f"Based on the takeoff and SOO for {p['name']}, what BMS scope items "
             f"might be missing before I finalise the proposal?", p, k)

    st.divider()

    # Device Q&A
    if tags:
        st.markdown("**Device scope question**")
        a1,a2 = st.columns([1,2])
        tag    = a1.selectbox("Device tag", tags, key="ai_tag")
        qtype  = a2.selectbox("Question", [
            "What BMS control points are needed?",
            "What is the control sequence?",
            "How do I handle this discrepancy?",
            "Estimate labor hours",
            "BACnet integration requirements",
        ], key="ai_qt")
        rec    = next((e for e in equip if e.get("tag")==tag),{})
        custom = st.text_area("Additional context (optional)",
                               placeholder="e.g. Niagara 4 front-end, back-of-house location…",
                               height=60, key="ai_ctx")
        if st.button("Ask Claude →", type="primary", key="ai_dev"):
            _ask(_device_prompt(tag, rec, qtype, custom, p["name"]), p, k)

    st.divider()
    st.markdown("**Freeform question**")
    fq = st.text_area("Ask anything about this project…", height=80, key="ai_free")
    if st.button("Ask →", key="ai_free_btn") and fq:
        _ask(fq, p, k)

    proj_hist = [h for h in st.session_state.ai_history if h.get("project")==p["name"]]
    if proj_hist:
        st.divider()
        st.markdown("**Session history**")
        for h in reversed(proj_hist[-6:]):
            with st.expander(h["q"][:70]):
                st.markdown(h["a"])

def _ask(prompt, p, k):
    ctx = (f"Project: {p['name']} | Client: {p.get('client','—')} | "
           f"Address: {p.get('address','—')} | Bid: {p.get('bid_date','—')} | "
           f"Docs: {', '.join(p.get('doc_names',{}).keys())} | "
           f"Devices: {len(p['takeoff'].get('equipment',[]))} | "
           f"Discrepancies: {len(p['takeoff'].get('discrepancies',[]))} | "
           f"Points: {len(p['point_list'].get('rows',[]))} | "
           f"Estimate lines: {len(p['estimate'].get('lines',[]))}\n"
           f"You are a senior BMS estimator with 20 years NYC commercial experience.\n\n")
    with st.spinner("Claude is thinking…"):
        resp = _claude(k, ctx+prompt, 2000)
    if resp:
        st.markdown("---"); st.markdown(resp)
        st.session_state.ai_history.append({"project":p["name"],"q":prompt[:80],"a":resp})

def _device_prompt(tag, rec, qtype, extra, proj):
    qmap = {
        "What BMS control points are needed?":
            "List all BMS points (AI/AO/DI/DO/Network) as a table: type, description, units, normal range.",
        "What is the control sequence?":
            "Write a concise SOO-style control sequence: startup/shutdown, setpoint, alarms, interlocks.",
        "How do I handle this discrepancy?":
            "Device is in schedule but missing from SOO. What BMS scope is typically needed? What to ask the engineer?",
        "Estimate labor hours":
            "Estimate hours by phase: Engineering, Programming, Integration, Graphics, Startup. Show reasoning.",
        "BACnet integration requirements":
            "BACnet object types, instance numbering, required writable objects, vendor-specific notes.",
    }
    return (f"Project: {proj} | Device: {tag} | System: {rec.get('system','?')} | "
            f"Floor: {rec.get('floor','?')} | Classification: {rec.get('classification','?')} | "
            f"BMS interface: {rec.get('bms_interface_default',rec.get('bms_interface','?'))} | "
            f"SOO status: {'NOT IN SOO — discrepancy' if rec.get('discrepancy_flag') else 'confirmed'}"
            + (f" | Extra: {extra}" if extra else "")
            + f"\n\n{qmap.get(qtype,qtype)}")

# ── AI calls ──────────────────────────────────────────────────────────────────
def _claude(k, prompt, max_tokens=1500):
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=k)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            messages=[{"role":"user","content":prompt}]
        )
        return msg.content[0].text
    except Exception as e:
        err = str(e)
        if "401" in err or "authentication" in err.lower() or "invalid" in err.lower():
            st.error(
                "❌ **Invalid API key.** Go to [Streamlit Cloud dashboard]"
                "(https://share.streamlit.io) → your app → ⋮ → Settings → Secrets "
                "and add:\n```\nANTHROPIC_API_KEY = \"sk-ant-your-key-here\"\n```"
            )
        elif "429" in err:
            st.error("❌ Rate limit hit. Wait 30 seconds and try again.")
        else:
            st.error(f"❌ Claude error: {err}")
        return None

def _extract_pdf_text(pdf_bytes, max_chars=12000):
    """Extract text from PDF using PyMuPDF. Returns truncated text for Claude."""
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_text = []
        for i, page in enumerate(doc):
            text = page.get_text().strip()
            if text:
                pages_text.append(f"--- PAGE {i+1} ---\n{text}")
        full = "\n".join(pages_text)
        # Truncate to max_chars to stay within token limits
        if len(full) > max_chars:
            full = full[:max_chars] + f"\n[...truncated at {max_chars} chars]"
        return full
    except Exception as e:
        return f"[Could not extract text: {e}]"


def _extract_docx_text(docx_bytes, max_chars=8000):
    """Extract text from DOCX."""
    try:
        from docx import Document as D
        doc = D(io.BytesIO(docx_bytes))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return text[:max_chars]
    except Exception as e:
        return f"[Could not extract text: {e}]"


def ai_takeoff(p, k):
    """
    Real AI takeoff — extracts text from uploaded PDFs and sends to Claude.
    Reads: Drawings (schedule pages) + SOO (cross-check) + Controls spec (scope).
    """
    docs      = p.get("docs", {})
    doc_names = p.get("doc_names", {})

    # ── Extract text from each document ──────────────────────────────────
    extracted = {}
    for label in ["Drawings", "SOO", "Controls spec"]:
        raw_bytes = docs.get(label)
        if not raw_bytes:
            extracted[label] = None
            continue
        fname = doc_names.get(label, "")
        if fname.lower().endswith(".docx"):
            extracted[label] = _extract_docx_text(raw_bytes)
        else:
            # PDF — drawings get more characters, SOO gets medium
            max_c = 14000 if label == "Drawings" else 8000
            extracted[label] = _extract_pdf_text(raw_bytes, max_chars=max_c)

    # ── Build prompt with real content ────────────────────────────────────
    drawings_text = extracted.get("Drawings") or "Not provided"
    soo_text      = extracted.get("SOO")      or "Not provided"
    spec_text     = extracted.get("Controls spec") or "Not provided"

    prompt = f"""You are a senior BMS estimation expert reviewing mechanical drawings for project '{p['name']}'.

DRAWINGS TEXT (schedule sheets and floor plans):
{drawings_text}

SEQUENCE OF OPERATIONS (SOO):
{soo_text}

CONTROLS SPECIFICATION:
{spec_text[:4000] if spec_text != "Not provided" else "Not provided"}

TASK:
1. Extract ALL unique BMS device tags from the drawings text above.
2. For each tag, check if it appears in the SOO text. If it has no SOO sequence, flag as discrepancy.
3. Common discrepancies: EUH (electric unit heaters) and UH (hot water unit heaters) with integral/wall thermostats — these appear in schedules but rarely have SOO sequences.

Return ONLY valid JSON in this exact format:
{{
  "equipment": [
    {{
      "tag": "FCU-SC-1",
      "qty": 1,
      "floor": "Subcellar",
      "system": "Fan Coil Unit",
      "classification": "Terminal / FCU",
      "bms_interface_default": "DDC",
      "soo_confirmed": true,
      "discrepancy_flag": false,
      "action": ""
    }}
  ],
  "discrepancies": [
    {{
      "tag": "EUH-SC-1",
      "system": "Electric Unit Heater",
      "floor": "Subcellar",
      "action": "Integral thermostat — confirm whether BMS monitoring point is required"
    }}
  ]
}}

Device types to extract: FCU, AHU, DOAS, MUA, VAV, EUH, UH, ASHP, ERV, PFSP, SPF, HPF, GX, EF, HF, TF, PCHWP, SCHWP, PHWP, SHWP, FPP, PFHX, BT, GFU, FOP, ESP, FTR, HWC, ACU, AC-C.

Floor mapping from tag suffix: SC=Subcellar, C=Cellar, 1M=1st/Mezzanine, 12=12th Floor, 33=33rd Floor, 34=34th Floor, 35=35th Floor, 36=36th Floor, ROOF=Roof.

Return ONLY the JSON, no other text."""

    raw = _claude(k, prompt, 4000) or ""

    try:
        clean = raw.strip()
        if "```" in clean:
            parts = clean.split("```")
            clean = parts[1] if len(parts) > 1 else clean
            if clean.startswith("json"):
                clean = clean[4:]
        return json.loads(clean.strip())
    except Exception:
        # If JSON parse fails, return error with raw output for debugging
        return {
            "equipment": [],
            "discrepancies": [],
            "error": f"JSON parse failed. Raw output: {raw[:500]}"
        }

def ai_point_list(p, k, pl_tmpl, pl_name):
    """Generate BMS point list from SOO. Works with or without takeoff."""

    # ── Column format ─────────────────────────────────────────────────────
    columns = ["System/Device","Tag","Description","Qty","AI","AO","DI","DO","HWI","Network","Notes"]
    if pl_tmpl:
        try:
            df_t = pd.read_excel(io.BytesIO(pl_tmpl), nrows=3)
            cols = [str(c) for c in df_t.columns if not str(c).startswith("Unnamed")]
            if cols: columns = cols
        except Exception:
            pass
    col_str = ", ".join(f'"{c}"' for c in columns)

    # ── Extract SOO text ──────────────────────────────────────────────────
    soo_text, spec_text = "", ""
    if p["docs"].get("SOO"):
        fname = p["doc_names"].get("SOO","")
        soo_text = (_extract_docx_text(p["docs"]["SOO"], 10000)
                    if fname.lower().endswith(".docx")
                    else _extract_pdf_text(p["docs"]["SOO"], 10000))
    if p["docs"].get("Controls spec"):
        spec_text = _extract_pdf_text(p["docs"]["Controls spec"], 4000)

    # ── Device summary ────────────────────────────────────────────────────
    equip = p["takeoff"].get("equipment", [])
    if equip:
        from collections import Counter as _C
        sc = _C(e.get("system","Unknown") for e in equip)
        dev_note = "Devices in takeoff: " + "; ".join(f"{v}x {k}" for k,v in sc.most_common(20))
    else:
        dev_note = "No takeoff yet — identify all systems from the SOO and generate points for each."

    # ── Example row using actual columns ─────────────────────────────────
    ex = {}
    for c in columns:
        if c in ("System/Device",): ex[c] = "DOAS-1M-1"
        elif c in ("Tag",):         ex[c] = "Supply Fan Start/Stop"
        elif c in ("Description",): ex[c] = "Supply fan enable command"
        elif c in ("Qty",):         ex[c] = 1
        elif c in ("DO","AO"):      ex[c] = "1"
        else:                       ex[c] = ""

    prompt = f"""You are a senior BMS controls engineer. Generate a point list for project '{p["name"]}'.

{dev_note}

SEQUENCE OF OPERATIONS — read every section and extract ALL I/O points listed:
{soo_text[:8000] if soo_text else "Not provided."}

CONTROLS SPEC:
{spec_text[:2000] if spec_text else "Not provided."}

OUTPUT RULES:
- Return a JSON array of objects, one row per BMS point
- Use EXACTLY these column names: {col_str}
- Use "1" for present, "" for not applicable
- Cover every system that has an I/O table in the SOO above (ASHP, HWP, CHWP, DOAS, MAU, AHU, ERV, FCU, VAV, ACU, HWC, FTR, GX, EF, ESP, GFU)
- Each system needs 5-20 rows for its individual points (fan SS, fan status, fan fault, valve, sensors, alarms)
- Do NOT summarise — one row per point

CRITICAL: Start your response with [ and end with ]. No markdown, no explanation, no code fences.

Example: {json.dumps([ex])}"""

    raw = _claude(k, prompt, max_tokens=4000) or ""

    # ── Robust JSON extraction ────────────────────────────────────────────
    def parse(text):
        text = text.strip()
        # Strip markdown fences
        if "```" in text:
            for part in text.split("```"):
                part = part.strip().lstrip("json").strip()
                if part.startswith("["): text = part; break
        # Trim to array bounds
        s, e = text.find("["), text.rfind("]")
        if s != -1 and e > s:
            return json.loads(text[s:e+1])
        raise ValueError("No array found")

    try:
        rows = parse(raw)
        if not isinstance(rows, list) or not rows:
            raise ValueError("Empty")
        # Ensure all columns present
        for row in rows:
            for col in columns:
                row.setdefault(col, "")
        return rows
    except Exception as exc:
        return [{c: ("Parse failed — check API key is valid in Streamlit Secrets"
                     if c == "System/Device"
                     else f"Error: {exc}" if c == "Tag"
                     else raw[:100] if c == "Description"
                     else "") for c in columns}]

def ai_estimate(p, k, rates, markup):
    pts  = len(p["point_list"].get("rows", []))
    devs = len(p["takeoff"].get("equipment", []))

    # Extract spec/SOO context for better estimates
    soo_text  = _extract_pdf_text(p["docs"]["SOO"],  max_chars=5000) if p["docs"].get("SOO")  else ""
    spec_text = _extract_pdf_text(p["docs"].get("Controls spec") or b"", max_chars=3000) if p["docs"].get("Controls spec") else ""

    has_takeoff  = devs > 0
    has_pl       = pts > 0

    if has_takeoff and has_pl:
        basis = f"Takeoff: {devs} devices. Point list: {pts} points."
    elif has_pl:
        basis = f"Point list: {pts} points (no takeoff loaded — device counts are estimated)."
    elif has_takeoff:
        basis = f"Takeoff: {devs} devices (no point list — estimating ~5 pts/device)."
        pts = devs * 5
    else:
        basis = "No takeoff or point list — estimating from SOO/spec scope only. Counts are rough."
        pts = 50  # rough default

    prompt = (
        f"Generate a BMS labor estimate for project '{p['name']}'.\n"
        f"Basis: {basis}\n"
        f"Labor rates: {json.dumps(rates)}. Markup: {markup}%.\n"
        f"SOO context: {soo_text[:3000] if soo_text else 'not provided'}\n"
        f"Controls spec: {spec_text[:2000] if spec_text else 'not provided'}\n\n"
        f"Hour formulas: Engineering=0.5×pts, Programming=1.0×pts, "
        f"Integration=0.5×pts, Graphics=0.5×pts, Startup=0.5×pts.\n"
        f"Group by system (FCUs, DOAS, Pumps, Heat Pumps, Life Safety, etc).\n"
        f"Return ONLY a JSON array:\n"
        f'[{{"System":"Fan Coil Units","Qty":8,"Points":40,'
        f'"Engineering (hrs)":20,"Programming (hrs)":40,"Integration (hrs)":20,'
        f'"Graphics (hrs)":20,"Startup (hrs)":20,"Total hrs":120,'
        f'"Rate ($/hr)":{rates.get("Programming",85)},"Total $":10200,'
        f'"Notes":"Based on SOO Section 1.10"}}]\n'
        f"Add rows for: panel/hardware allowance, engineering/submittal, "
        f"commissioning, project management.\n"
        f"Return ONLY the JSON array."
    )
    raw = _claude(k, prompt, 2500) or ""
    try:
        clean = raw.strip()
        if "```" in clean: clean = clean.split("```")[1]; clean = clean[4:] if clean.startswith("json") else clean
        return json.loads(clean.strip())
    except:
        return [{"System":"Parse error","Qty":0,"Points":0,
                 "Engineering (hrs)":0,"Programming (hrs)":0,"Integration (hrs)":0,
                 "Graphics (hrs)":0,"Startup (hrs)":0,"Total hrs":0,
                 "Rate ($/hr)":0,"Total $":0,"Notes":raw[:80]}]

def ai_proposal(p, k):
    cl      = st.session_state.clients.get(p.get("client"),{}) if p.get("client") else {}
    tmpl    = cl.get("prop_template_bytes")
    equip   = p["takeoff"].get("equipment",[])
    lines   = p["estimate"].get("lines",[])

    # Build scope from takeoff if available, otherwise from SOO
    if equip:
        agg = defaultdict(int)
        for e in equip: agg[e.get("system","Unknown")]+=1
        scope = "; ".join(f"{v}× {k}" for k,v in list(agg.items())[:15])
    else:
        # Extract scope from SOO
        soo_text = _extract_pdf_text(p["docs"]["SOO"], max_chars=4000) if p["docs"].get("SOO") else ""
        scope = f"Scope based on SOO (no takeoff loaded): {soo_text[:500]}..." if soo_text else "Scope to be confirmed"

    try:
        total = sum(float(r.get("Total $",0)) for r in lines)*(1+p["estimate"].get("markup",10)/100)
        price = f"${total:,.0f}"
    except: price = "[TO BE DETERMINED — complete estimate first]"
    tmpl_note = ""
    if tmpl:
        try:
            from docx import Document as D
            doc = D(io.BytesIO(tmpl))
            tmpl_note = "Template sections found:\n"+"\n".join(
                f"- {par.text}" for par in doc.paragraphs if par.text.strip() and len(par.text.strip())>3)[:600]
        except: tmpl_note = "Follow client proposal template structure."
    prompt = (
        f"Write a professional BMS proposal for '{p['name']}' addressed to {p.get('client','the client')}.\n"
        f"Address: {p.get('address','—')} | Bid date: {p.get('bid_date','—')}\n"
        f"Scope: {scope}\nBase scope price: {price}\n{tmpl_note}\n\n"
        f"Include: 1) Introduction 2) Basis of proposal 3) Scope of work (bullets per system) "
        f"4) Pricing 5) Notes & exclusions 6) Closing.\n"
        f"Use 'We will provide...' language. TEC Building Systems proposal style.\nReturn full proposal text."
    )
    result = _claude(k, prompt, max_tokens=3000)
    if not result:
        return "[Error: Claude returned empty response. Check your API key in Streamlit Secrets.]"
    return result

# ── Export ────────────────────────────────────────────────────────────────────
def export_pl_excel(df, tmpl_bytes=None):
    from openpyxl import load_workbook, Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    if tmpl_bytes:
        try:
            wb = load_workbook(io.BytesIO(tmpl_bytes))
            ws = wb.active
            hr = 1
            for row in ws.iter_rows(min_row=1,max_row=10):
                if any(c.value for c in row): hr=row[0].row; break
            tcols = {ws.cell(hr,c).value:c for c in range(1,ws.max_column+1) if ws.cell(hr,c).value}
            for ri,rd in enumerate(df.to_dict("records")):
                for cn,ci in tcols.items():
                    if cn in rd: ws.cell(hr+1+ri,ci,rd[cn])
            out=io.BytesIO(); wb.save(out); return out.getvalue()
        except: pass
    wb=Workbook(); ws=wb.active; ws.title="Point List"
    cols=list(df.columns)
    fill=PatternFill("solid",start_color="2E75B6")
    for ci,col in enumerate(cols,1):
        cell=ws.cell(1,ci,col)
        cell.font=Font(bold=True,color="FFFFFF",name="Arial",size=10)
        cell.fill=fill; cell.alignment=Alignment(horizontal="center")
        ws.column_dimensions[cell.column_letter].width=max(14,len(str(col))+4)
    for ri,row in enumerate(df.to_dict("records"),2):
        for ci,col in enumerate(cols,1): ws.cell(ri,ci,row.get(col,""))
    out=io.BytesIO(); wb.save(out); return out.getvalue()

def export_prop_docx(text, p, tmpl_bytes=None):
    from docx import Document as D
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    if tmpl_bytes:
        try:
            doc=D(io.BytesIO(tmpl_bytes))
            repls={"{{PROJECT_NAME}}":p["name"],"{{ADDRESS}}":p.get("address",""),
                   "{{CLIENT}}":p.get("client",""),"{{DATE}}":str(date.today()),
                   "{{SCOPE_TEXT}}":text}
            for para in doc.paragraphs:
                for k,v in repls.items():
                    if k in para.text:
                        for run in para.runs: run.text=run.text.replace(k,v)
            found=any("{{SCOPE_TEXT}}" in para.text for para in doc.paragraphs)
            if not found:
                doc.add_page_break()
                for line in text.split("\n"): doc.add_paragraph(line)
            out=io.BytesIO(); doc.save(out); return out.getvalue()
        except: pass
    doc=D()
    t=doc.add_heading(p["name"],0); t.alignment=WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"Date: {date.today()}")
    doc.add_paragraph(f"Address: {p.get('address','')}")
    doc.add_paragraph(f"Client: {p.get('client','')}")
    doc.add_paragraph()
    for line in text.split("\n"):
        if line.startswith("# "): doc.add_heading(line[2:],1)
        elif line.startswith("## "): doc.add_heading(line[3:],2)
        elif line.startswith("- "): doc.add_paragraph(line[2:],style="List Bullet")
        elif line.strip(): doc.add_paragraph(line)
        else: doc.add_paragraph()
    out=io.BytesIO(); doc.save(out); return out.getvalue()

# ── Reports ───────────────────────────────────────────────────────────────────
def page_reports():
    st.title("Reports")
    st.info("Coming soon: cross-project pipeline analytics, win/loss tracking, device type trends.")

# ── Product status panel ──────────────────────────────────────────────────────

MODULE_READINESS = [
    {
        "module":   "Takeoff",
        "icon":     "📐",
        "ready":    95,
        "status":   "production",
        "what_works": [
            "Text-layer tag extraction from CAD PDFs",
            "Schedule page auto-detection",
            "SOO cross-check (3-way: schedule × SOO × drawing)",
            "Amber/red/green/blue status per device",
            "West 34th Hotel: 109 devices, 12 discrepancies confirmed",
        ],
        "gaps": [
            "AI Takeoff button reads doc names, not PDF content — use PDF extraction instead",
        ],
        "next": "Wire Claude Vision to read floor plan images for scanned PDFs",
    },
    {
        "module":   "Drawing Markup",
        "icon":     "🖊",
        "ready":    90,
        "status":   "production",
        "what_works": [
            "Search any tag → jump to page with highlight",
            "Annotated PDF download with all 4 status colors",
            "Legend page + summary overlay on page 1",
            "Amber tags → Clarifications, Red tags → Exclusions (one click)",
            "Progress bar with page count and schedule page detection",
        ],
        "gaps": [
            "Page preview render speed depends on PDF size",
            "Rotated or very small tags may be missed",
        ],
        "next": "Add thumbnail strip to browse all pages; add zoom on page preview",
    },
    {
        "module":   "Point List",
        "icon":     "📋",
        "ready":    65,
        "status":   "demo",
        "what_works": [
            "AI generates AI/AO/DI/DO per device from context",
            "Client Excel template: AI matches your column format",
            "Editable table — change any cell before export",
            "Export to Excel (plain or matching client template)",
        ],
        "gaps": [
            "AI reads device names, not actual SOO line by line",
            "Point counts are estimated, not extracted from SOO",
        ],
        "next": "Extract SOO text per system, send to Claude for exact point list",
    },
    {
        "module":   "Estimate",
        "icon":     "💰",
        "ready":    70,
        "status":   "demo",
        "what_works": [
            "Labor: AI generates hours by phase from point count + rates",
            "Material: 200-item Honeywell price book, qty × unit cost",
            "Client labor rates saved per client profile",
            "Combined total: Labor + Material with markup",
            "Export to Excel (labor / material / combined sheets)",
        ],
        "gaps": [
            "Labor hours are formula-based, not read from controls spec",
            "Material prices are 2022 list prices",
            "No material take-off from drawings yet",
        ],
        "next": "Read controls spec for inclusions/exclusions; connect price book to vendor API",
    },
    {
        "module":   "Proposal",
        "icon":     "📄",
        "ready":    60,
        "status":   "demo",
        "what_works": [
            "AI writes TEC-style proposal from scope summary",
            "Clarifications auto-filled from amber tags",
            "Exclusions auto-filled from red tags",
            "Client Word template: fills {{placeholders}}",
            "Export to .docx",
        ],
        "gaps": [
            "AI writes from scope summary, not from reading your actual proposal template sections",
            "Needs human review before sending to client",
        ],
        "next": "Parse Word template sections, fill each section individually with targeted AI",
    },
    {
        "module":   "AI Advisor",
        "icon":     "🤖",
        "ready":    80,
        "status":   "production",
        "what_works": [
            "Full project context in every call",
            "Device-level Q&A: points, sequence, discrepancy resolution, labor hours",
            "Quick actions: resolve discrepancies, review estimate, scope gap check",
            "Session history per project",
        ],
        "gaps": [
            "Context is metadata only — doesn't read uploaded PDF content",
        ],
        "next": "Pass extracted PDF text as context for richer, document-grounded answers",
    },
]

PRODUCTION_GAPS = [
    {
        "gap":      "Persistent storage",
        "effort":   "2-3 weeks",
        "impact":   "HIGH",
        "why":      "Everything lives in session state — disappears on refresh. "
                    "Needs Supabase (Postgres) for projects, clients, estimates to persist. "
                    "Foundation for everything else below.",
        "status":   "Partial — Streamlit storage saves metadata. Uploaded PDFs not persisted.",
    },
    {
        "gap":      "User accounts",
        "effort":   "1 week",
        "impact":   "HIGH",
        "why":      "No login = no separation between users. "
                    "Supabase auth (email or Google) solves this once storage exists.",
        "status":   "Not started",
    },
    {
        "gap":      "Multi-user / team support",
        "effort":   "2-3 weeks",
        "impact":   "MEDIUM",
        "why":      "Two estimators get separate sessions with no shared data. "
                    "Need shared project state, role-based access (estimator / reviewer / PM), "
                    "conflict resolution when two people edit simultaneously.",
        "status":   "Not started",
    },
    {
        "gap":      "Audit trail",
        "effort":   "1-2 weeks",
        "impact":   "MEDIUM",
        "why":      "No record of who changed what, when. "
                    "Critical for bid review and dispute resolution. "
                    "Every module change logged: user, field, old value, new value, timestamp.",
        "status":   "Not started",
    },
    {
        "gap":      "Real PDF parsing pipeline",
        "effort":   "2-3 weeks",
        "impact":   "HIGH",
        "why":      "AI Takeoff currently reads doc names, not content. "
                    "Production: extract schedule page text → Claude structured extraction; "
                    "render floor plan pages as images → Claude Vision for symbol detection.",
        "status":   "Partial — text search works; Claude Vision call not wired",
    },
    {
        "gap":      "Price book maintenance",
        "effort":   "1 week",
        "impact":   "LOW",
        "why":      "Prices change quarterly. Currently 2022 list prices hardcoded in JSON. "
                    "Need UI to edit items, import from Excel, or connect to vendor API.",
        "status":   "JSON structure ready — UI not built",
    },
    {
        "gap":      "Mobile / field use",
        "effort":   "2-4 weeks",
        "impact":   "LOW",
        "why":      "Estimators review drawings on site. "
                    "Streamlit is desktop-first. Real mobile needs responsive layout "
                    "or separate React frontend.",
        "status":   "Not started",
    },
]


def _product_status_panel():
    st.markdown("### Product status & roadmap")
    st.caption(
        "West 34th Street Hotel as reference project · "
        "Honest assessment of what's working, what's in progress, and what's next"
    )

    # ── Overall readiness bar ─────────────────────────────────────────────
    st.divider()
    st.markdown("#### Overall tool readiness")

    avg_ready = sum(m["ready"] for m in MODULE_READINESS) // len(MODULE_READINESS)
    prod_count  = sum(1 for m in MODULE_READINESS if m["status"] == "production")
    demo_count  = sum(1 for m in MODULE_READINESS if m["status"] == "demo")

    oc1, oc2, oc3, oc4 = st.columns(4)
    oc1.metric("Overall readiness",  f"{avg_ready}%")
    oc2.metric("Production-ready modules", prod_count)
    oc3.metric("Demo-ready modules",  demo_count)
    oc4.metric("Roadmap items",       len(PRODUCTION_GAPS))

    st.progress(avg_ready / 100,
                text=f"{avg_ready}% ready · {prod_count} modules production-ready · {demo_count} demo-ready")

    # ── Per-module readiness ──────────────────────────────────────────────
    st.divider()
    st.markdown("#### Module readiness")

    for mod in MODULE_READINESS:
        status_color = (
            "🟢" if mod["status"] == "production" else
            "🟡" if mod["status"] == "demo" else "🔴"
        )
        status_label = (
            "Production-ready" if mod["status"] == "production" else
            "Demo-ready" if mod["status"] == "demo" else "Not ready"
        )
        with st.expander(
            f"{mod['icon']} {mod['module']} — {mod['ready']}% · {status_color} {status_label}",
            expanded=False
        ):
            st.progress(mod["ready"] / 100)

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**✅ What works**")
                for w in mod["what_works"]:
                    st.markdown(f"- {w}")
            with c2:
                st.markdown("**⚠️ Gaps**")
                for g in mod["gaps"]:
                    st.markdown(f"- {g}")

            st.markdown(f"**➡ Next:** {mod['next']}")

    # ── Production gaps ───────────────────────────────────────────────────
    st.divider()
    st.markdown("#### What a production version needs")
    st.caption("Ordered by impact. Total estimate: 3-4 months part-time.")

    IMPACT_COLOR = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "⚪"}

    for gap in PRODUCTION_GAPS:
        ic = IMPACT_COLOR.get(gap["impact"], "⚪")
        with st.expander(
            f"{ic} {gap['gap']} — {gap['effort']} · Impact: {gap['impact']}",
            expanded=False
        ):
            st.markdown(f"**Why it matters:** {gap['why']}")
            st.markdown(f"**Current status:** {gap['status']}")

    # ── Setup checklist ──────────────────────────────────────────────────
    st.divider()
    st.markdown("#### 📋 Setup checklist")

    checks = [
        ("Load West 34th JSON",
         "Takeoff tab → 'Or upload schedule_ground_truth.json'. "
         "Gives 109 real devices and 12 discrepancies. Do NOT use AI Takeoff button live."),
        ("Run drawing markup on your 15MB set",
         "Upload real drawing set, click Process, verify highlights look right, "
         "generate annotated PDF once and keep ready."),
        ("Add API key to Streamlit Secrets",
         "Streamlit dashboard → Settings → Secrets → "
         "ANTHROPIC_API_KEY = 'sk-ant-...'"),
        ("Practise the product walkthrough",
         "Overview → Discrepancies → Drawing Markup search → "
         "Send to proposal → Open this panel. Out loud, 3 times."),
        ("Know the roadmap for every incomplete tab",
         "Each tab that shows partial output has a clear next step in the roadmap panel."),
    ]

    all_done = True
    for i, (title, desc) in enumerate(checks, 1):
        done = st.checkbox(f"**{i}. {title}**", key=f"check_{i}")
        if not done:
            all_done = False
            st.caption(f"   → {desc}")

    if all_done:
        st.success("✅ All set — ready to go.")

    # ── Walkthrough script ────────────────────────────────────────────────
    st.divider()
    with st.expander("📣 Product walkthrough script"):
        st.markdown("""
**Beat 1 — The problem** *(60 sec)*
> *"A typical BMS estimate touches 5 documents, takes 2-3 days, and still misses things.
The most common miss: devices in the schedule with no SOO sequence.
Nobody writes them as excluded, nobody includes them in scope. They fall through the gap."*

---
**Beat 2 — The catch** *(90 sec)*

Open **Discrepancies** tab → point to amber banner.

> *"This project has 12 unit heaters in the M-200 schedule with integral thermostats
and zero SOO sequence. The tool caught them automatically.
Each one is a $500–700 scope question. Potentially $8,000 missed."*

Open **Drawing Markup** → search `UH-SC-1`.

> *"It's physically here on the drawing, it's in the schedule —
but there's no SOO sequence. Is it in BMS scope or not?
The tool forces that question before you submit the number."*

---
**Beat 3 — The pipeline** *(90 sec)*

Click through the 5 module tabs quickly.

> *"Once the takeoff is clean, the tool generates the point list in the client's
own Excel format, estimates labor from the point count,
builds the material list from our price book,
and drafts the proposal in our Word template.
The estimator reviews — AI does the first pass."*

Click **Send amber tags to proposal** → show Clarifications auto-filled.

---
**Beat 4 — Honest roadmap** *(60 sec)*

Open **this panel**.

> *"Here's what's production-ready, what's demo-ready, and what's missing.
Biggest gap: persistent storage — session state disappears on refresh.
Second: multi-user. Both are 6-8 week engineering problems,
not architecture problems — the data model already supports them."*

---
**Close**

> *"The core insight — three-way cross-check of schedule, SOO, and drawings —
is what's actually new. Everything else is workflow automation around that insight.
The architecture is modular so each piece can become an API
that plugs into whatever system you're already using."*
        """)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    init(); sidebar()
    nav = st.session_state.nav
    if nav=="Overview":  page_overview()
    elif nav=="Projects":page_projects()
    elif nav=="Reports": page_reports()

if __name__=="__main__":
    main()
