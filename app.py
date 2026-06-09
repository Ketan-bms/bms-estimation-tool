"""
BMS Estimation Tool — app.py v2
Complete multi-project estimating platform.
Run: streamlit run app.py
"""

import json, os, io, base64
from material_module import module_material, init_pricebooks
from markup_ui import module_markup
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
# ── Persistent storage helpers ───────────────────────────────────────────────

def _storage_save(key, value):
    """Save to Streamlit persistent storage. Falls back silently if unavailable."""
    try:
        import json
        storage = st.connection("storage", type="st.connections.StorageConnection")             if hasattr(st, "connection") else None
        if storage:
            storage.put(key, json.dumps(value, default=str))
            return True
    except Exception:
        pass
    # Fallback: use window.storage via components if available
    try:
        import streamlit.components.v1 as components
        import json
        js = f"""
        <script>
        try {{
            window.parent.localStorage.setItem({json.dumps(key)}, {json.dumps(json.dumps(value, default=str))});
        }} catch(e) {{}}
        </script>
        """
        components.html(js, height=0)
    except Exception:
        pass
    return False


def _storage_load(key, default=None):
    """Load from persistent storage."""
    try:
        storage = st.connection("storage", type="st.connections.StorageConnection")             if hasattr(st, "connection") else None
        if storage:
            import json
            raw = storage.get(key)
            if raw:
                return json.loads(raw)
    except Exception:
        pass
    return default


def _save_app_state():
    """Persist clients and projects to storage."""
    import json
    try:
        # Save clients (without binary template bytes — too large)
        clients_serializable = {}
        for cname, c in st.session_state.get("clients", {}).items():
            clients_serializable[cname] = {
                k: v for k, v in c.items()
                if k not in ("pl_template_bytes", "prop_template_bytes")
            }
        # Save projects (without doc bytes — too large for storage)
        projects_serializable = {}
        for pname, p in st.session_state.get("projects", {}).items():
            projects_serializable[pname] = {
                k: v for k, v in p.items()
                if k not in ("docs",)
            }
        _storage_save("bms_clients",  clients_serializable)
        _storage_save("bms_projects", projects_serializable)
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

    # Load persisted data on first run
    if not st.session_state.get("storage_loaded"):
        saved_clients  = _storage_load("bms_clients",  {})
        saved_projects = _storage_load("bms_projects", {})
        if saved_clients:
            # Merge — don't overwrite if session already has data
            for k,v in saved_clients.items():
                if k not in st.session_state["clients"]:
                    st.session_state["clients"][k] = v
        if saved_projects:
            for k,v in saved_projects.items():
                if k not in st.session_state["projects"]:
                    # Re-attach empty docs dict (bytes not persisted)
                    v.setdefault("docs", {})
                    v.setdefault("doc_names", {})
                    st.session_state["projects"][k] = v
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
    idx = MODULE_ORDER.index(mod)
    if idx == 0: return False
    return module_status(p, MODULE_ORDER[idx-1]) == "not_started"

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
        for label in ["Overview","Clients","Projects","Reports"]:
            active = st.session_state.nav == label
            if st.button(label, key=f"nav_{label}",
                         type="primary" if active else "secondary",
                         use_container_width=True):
                st.session_state.nav = label
                if label != "Projects": st.session_state.active_project = None
                st.rerun()
        if st.session_state.projects:
            st.divider()
            st.markdown('<p class="block-label">Projects</p>', unsafe_allow_html=True)
            for pname,p in st.session_state.projects.items():
                disc = len(p["takeoff"].get("discrepancies",[]))
                lbl = f"{'▶ ' if st.session_state.active_project==pname else ''}{pname}"
                if st.button(lbl, key=f"sb_{pname}", use_container_width=True):
                    st.session_state.active_project = pname
                    st.session_state.nav = "Projects"
                    st.session_state.active_module = "Takeoff"
                    st.rerun()
                if disc: st.caption(f"  ⚠️ {disc} discrepancies")
        st.divider()
        k = st.text_input("Anthropic API key", type="password",
                          value=os.environ.get("ANTHROPIC_API_KEY",""),
                          key="api_key_input")
        if k: st.session_state["anthropic_api_key"] = k

# ── Overview ──────────────────────────────────────────────────────────────────
def page_overview():
    st.title("Overview")
    today = date.today()
    projects = st.session_state.projects

    total_dev  = sum(len(p["takeoff"].get("equipment",[])) for p in projects.values())
    total_disc = sum(len(p["takeoff"].get("discrepancies",[])) for p in projects.values())
    est_ready  = sum(1 for p in projects.values() if module_status(p,"Estimate")=="done")

    nearest_days, nearest_name = None, None
    for pname,p in projects.items():
        bd = p.get("bid_date")
        if bd:
            try:
                d = (date.fromisoformat(str(bd))-today).days
                if d>=0 and (nearest_days is None or d<nearest_days):
                    nearest_days,nearest_name = d,pname
            except: pass

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Active projects",  len(projects))
    c2.metric("Total devices",    total_dev)
    c3.metric("Discrepancies",    total_disc,
              delta=f"{total_disc} need resolution" if total_disc else None,
              delta_color="inverse" if total_disc else "normal")
    c4.metric("Estimates ready",  f"{est_ready} of {len(projects)}")

    st.divider()
    col_l, col_r = st.columns([1.6,1])

    with col_l:
        st.markdown("**Projects — pipeline**")
        if not projects:
            st.info("No projects yet. Go to Projects → New project.")
        else:
            # Header row
            cols = st.columns([2,1,1,1,1,1,1])
            for c,h in zip(cols,["Project","Devices","Takeoff","Point list","Estimate","Proposal","Bid"]):
                c.markdown(f'<span style="font-size:11px;color:#64748b;font-weight:500">{h}</span>',
                           unsafe_allow_html=True)
            for pname,p in projects.items():
                row = st.columns([2,1,1,1,1,1,1])
                disc = len(p["takeoff"].get("discrepancies",[]))
                devs = len(p["takeoff"].get("equipment",[]))
                bd = str(p.get("bid_date","—"))[:10]
                row[0].markdown(f"**{pname}**")
                row[1].markdown(str(devs))
                for i,mod in enumerate(MODULE_ORDER):
                    s = module_status(p,mod)
                    lbl = f"⚠️ {disc}" if mod=="Takeoff" and disc else ("Done" if s=="done" else ("In progress" if s=="in_progress" else "—"))
                    row[2+i].markdown(chip("issues" if mod=="Takeoff" and disc else s, lbl),
                                      unsafe_allow_html=True)
                row[6].markdown(bd)
            if st.button("+ New project", key="ov_new"):
                st.session_state.nav = "Projects"
                st.session_state.active_project = None
                st.rerun()

    with col_r:
        st.markdown("**Bid deadlines**")
        if not projects:
            st.caption("No projects.")
        else:
            for pname,p in projects.items():
                bd = p.get("bid_date")
                if bd:
                    try:
                        days = (date.fromisoformat(str(bd))-today).days
                        icon = "🔴" if days<=30 else "🟡" if days<=60 else "🟢"
                        st.markdown(f"{icon} **{pname}** — {days}d · {bd}")
                    except: st.markdown(f"**{pname}** — {bd}")
        st.divider()
        st.markdown("**Needs attention**")
        any_alert = False
        for pname,p in projects.items():
            disc = p["takeoff"].get("discrepancies",[])
            if disc:
                any_alert = True
                st.warning(f"⚠️ **{pname}** — {len(disc)} discrepancies")
            bd = p.get("bid_date")
            if module_status(p,"Takeoff")!="not_started" and module_status(p,"Point List")=="not_started" and bd:
                try:
                    days = (date.fromisoformat(str(bd))-today).days
                    if days<=45:
                        any_alert = True
                        st.info(f"⏰ **{pname}** — point list not started, {days}d to bid")
                except: pass
        if not any_alert:
            st.success("All clear — no blocking issues")

    # ── Product status panel (collapsible — for interview use) ────────────────
    st.divider()
    with st.expander("🗺 Product status & roadmap — click to expand during interview"):
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
            c1,c2 = st.columns(2)
            pname    = c1.text_input("Project name *")
            address  = c2.text_input("Address")
            c3,c4   = st.columns(2)
            client_opts = ["(no client)"] + list(st.session_state.clients.keys())
            client   = c3.selectbox("Client", client_opts)
            bid_date = c4.date_input("Bid date", value=None)
            if client == "(no client)": client = None

            st.markdown("**Upload project documents**")
            d1,d2,d3,d4 = st.columns(4)
            draw_f = d1.file_uploader("Drawings (PDF)",  type=["pdf"],        key="np_draw")
            soo_f  = d2.file_uploader("SOO (PDF/DOCX)",  type=["pdf","docx"], key="np_soo")
            spec_f = d3.file_uploader("Controls spec",   type=["pdf","docx"], key="np_spec")
            epl_f  = d4.file_uploader("Existing point list (xlsx)", type=["xlsx"], key="np_epl")

            if st.form_submit_button("Create project", type="primary"):
                if not pname:
                    st.error("Project name required.")
                elif pname in projects:
                    st.error("Name already exists.")
                else:
                    p = new_project(pname, client,
                                    str(bid_date) if bid_date else None, address)
                    for label,f in [("Drawings",draw_f),("SOO",soo_f),
                                    ("Controls spec",spec_f),("Existing point list",epl_f)]:
                        if f:
                            p["docs"][label]      = f.read()
                            p["doc_names"][label] = f.name
                    cl = st.session_state.clients.get(client,{}) if client else {}
                    p["estimate"]["rates"] = dict(cl.get("rates", DEFAULT_RATES))
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
    bc,hc = st.columns([1,8])
    if bc.button("← Back"):
        st.session_state.active_project = None
        st.rerun()
    hc.markdown(f"## {p['name']}")
    hc.caption(f"{p.get('address','—')} · Client: {p.get('client','—')} · Bid: {p.get('bid_date','TBD')}")

    # Build tab labels
    tab_labels = []
    for mod in MODULE_ORDER + ["AI Advisor"]:
        if mod == "AI Advisor":
            tab_labels.append("🤖 AI Advisor")
        elif module_locked(p, mod):
            tab_labels.append(f"🔒 {mod}")
        else:
            s = module_status(p,mod)
            icon = "✅" if s=="done" else "⚠️" if s=="issues" else "📋"
            tab_labels.append(f"{icon} {mod}")
    tab_labels.append("🖊 Drawing Markup")

    tabs = st.tabs(tab_labels)
    handlers = [module_takeoff, module_point_list, module_estimate,
                module_proposal, module_ai_advisor, module_markup]
    all_mods = MODULE_ORDER + ["AI Advisor", "Drawing Markup"]

    for tab, mod, handler in zip(tabs, all_mods, handlers):
        with tab:
            if mod not in ("AI Advisor", "Drawing Markup") and module_locked(p, mod):
                prev = MODULE_ORDER[MODULE_ORDER.index(mod)-1]
                st.info(f"🔒 Complete **{prev}** first to unlock this module.")
            else:
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
    col_btn,_ = st.columns([1,3])
    if col_btn.button("🤖 Run AI Takeoff", type="primary", key="run_tk"):
        k = api_key()
        if not k: st.error("Add API key in sidebar.")
        elif not p["docs"]: st.error("Upload at least one document first.")
        else:
            with st.spinner("Claude is extracting devices from your documents..."):
                result = ai_takeoff(p, k)
            p["takeoff"]["equipment"]     = result.get("equipment",[])
            p["takeoff"]["discrepancies"] = result.get("discrepancies",[])
            p["takeoff"]["status"]        = "issues" if result.get("discrepancies") else "done"
            st.rerun()

    with st.expander("Or upload schedule_ground_truth.json"):
        gt = st.file_uploader("JSON", type=["json"], key="tk_gt")
        if gt and st.button("Load JSON", key="tk_load"):
            data = json.load(gt)
            equip = data.get("equipment",[])
            p["takeoff"]["equipment"]     = equip
            p["takeoff"]["discrepancies"] = [e for e in equip if e.get("discrepancy_flag")]
            p["takeoff"]["status"]        = "issues" if p["takeoff"]["discrepancies"] else "done"
            st.success(f"Loaded {len(equip)} devices."); st.rerun()

    equip = p["takeoff"].get("equipment",[])
    discs = p["takeoff"].get("discrepancies",[])
    if not equip:
        st.info("No takeoff data. Run AI Takeoff or upload JSON.")
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

    if st.button("🤖 Generate point list", type="primary", key="gen_pl"):
        k = api_key()
        if not k: st.error("Add API key in sidebar.")
        elif not p["takeoff"].get("equipment"): st.error("Complete takeoff first.")
        else:
            with st.spinner("Claude is reading SOO and controls spec to generate point list..."):
                rows = ai_point_list(p, k, pl_tmpl, pl_name)
            p["point_list"]["rows"]   = rows
            p["point_list"]["status"] = "done"
            st.success(f"✅ {len(rows)} points generated."); st.rerun()

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
    client   = p.get("client")
    cl       = st.session_state.clients.get(client,{}) if client else {}
    prop_tmpl = cl.get("prop_template_bytes")
    prop_name = cl.get("prop_template_name","")

    if prop_tmpl:
        st.success(f"✅ Client template loaded: `{prop_name}` — AI will fill your Word template sections.")
        st.caption("Use {{PROJECT_NAME}}, {{CLIENT}}, {{DATE}}, {{SCOPE_TEXT}} as placeholders in your Word template.")
    else:
        st.info("No proposal template. AI generates a standard TEC-style proposal. Add template in Clients tab.")

    if st.button("🤖 Generate proposal", type="primary", key="gen_prop"):
        k = api_key()
        if not k: st.error("Add API key in sidebar.")
        else:
            with st.spinner("Claude is writing your proposal..."):
                text = ai_proposal(p, k)
            p["proposal"]["text"]   = text
            p["proposal"]["status"] = "done"
            st.rerun()

    text = p["proposal"].get("text","")
    if not text:
        st.info("No proposal yet. Click Generate."); return

    edited = st.text_area("Proposal text (editable)", value=text, height=520, key="prop_ed")
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
        msg = anthropic.Anthropic(api_key=k).messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            messages=[{"role":"user","content":prompt}])
        return msg.content[0].text
    except Exception as e:
        st.error(f"Claude error: {e}"); return None

def ai_takeoff(p, k):
    doc_names = p.get("doc_names",{})
    prompt = (
        f"You are a BMS estimation expert. Extract all BMS device tags for project '{p['name']}'.\n"
        f"Documents uploaded: {', '.join(doc_names.keys()) or 'none'}.\n\n"
        f"Return ONLY valid JSON:\n"
        f'{{"equipment":[{{"tag":"FCU-SC-1","qty":1,"floor":"Subcellar","system":"Fan Coil Unit",'
        f'"classification":"Terminal / FCU","bms_interface_default":"DDC","soo_confirmed":true,'
        f'"discrepancy_flag":false,"action":""}}],'
        f'"discrepancies":[{{"tag":"EUH-SC-1","system":"Electric Unit Heater","floor":"Subcellar",'
        f'"action":"Confirm BMS monitoring scope"}}]}}\n\n'
        f"Device types to look for: FCU, AHU, DOAS, VAV, EUH, UH, ASHP, ERV, PFSP, SPF, HPF, GX, EF, PCHWP, SCHWP, PHWP, SHWP, PFHX, BT, FOP.\n"
        f"Discrepancies = devices in schedule with no SOO sequence (EUH, UH with integral thermostats are most common).\n"
        f"Return ONLY the JSON."
    )
    raw = _claude(k, prompt, 2000) or ""
    try:
        clean = raw.strip()
        if "```" in clean: clean = clean.split("```")[1]; clean = clean[4:] if clean.startswith("json") else clean
        return json.loads(clean.strip())
    except: return {"equipment":[],"discrepancies":[],"error":raw[:200]}

def ai_point_list(p, k, pl_tmpl, pl_name):
    col_desc = "Standard columns: System/Device, Tag, Description, Qty, AI, AO, DI, DO, HWI, Network, Notes"
    if pl_tmpl:
        try:
            df = pd.read_excel(io.BytesIO(pl_tmpl), nrows=2)
            col_desc = f"Match these client template columns exactly: {', '.join(str(c) for c in df.columns)}"
        except: pass
    equip = p["takeoff"].get("equipment",[])[:30]
    prompt = (
        f"Generate a BMS point list for '{p['name']}'.\n{col_desc}\n"
        f"Devices (sample): {json.dumps(equip)}\n"
        f"SOO: {p['doc_names'].get('SOO','not provided')} | Spec: {p['doc_names'].get('Controls spec','not provided')}\n"
        f"For each device list all required BMS points. Use '1' for present, '' for N/A.\n"
        f'Example: {{"System/Device":"FCU-SC-1","Tag":"Fan Enable","Description":"Fan start/stop","Qty":1,"AI":"","AO":"","DI":"","DO":"1","HWI":"","Network":"","Notes":""}}\n'
        f"Return ONLY a JSON array."
    )
    raw = _claude(k, prompt, 3000) or ""
    try:
        clean = raw.strip()
        if "```" in clean: clean = clean.split("```")[1]; clean = clean[4:] if clean.startswith("json") else clean
        return json.loads(clean.strip())
    except: return [{"System/Device":"Parse error","Tag":raw[:80],"Description":"","Qty":"","AI":"","AO":"","DI":"","DO":"","HWI":"","Network":"","Notes":""}]

def ai_estimate(p, k, rates, markup):
    pts   = len(p["point_list"].get("rows",[]))
    devs  = len(p["takeoff"].get("equipment",[]))
    prompt = (
        f"Generate a BMS estimate for '{p['name']}'. Points: {pts}, Devices: {devs}.\n"
        f"Labor rates: {json.dumps(rates)}. Markup: {markup}%.\n"
        f"Docs: {', '.join(p.get('doc_names',{}).keys())}.\n"
        f"Hour formulas: Engineering=0.5×pts, Programming=1.0×pts, Integration=0.5×pts, Graphics=0.5×pts, Startup=0.5×pts.\n"
        f"Return ONLY a JSON array:\n"
        f'[{{"System":"Fan Coil Units (Subcellar)","Qty":8,"Points":40,"Engineering (hrs)":20,'
        f'"Programming (hrs)":40,"Integration (hrs)":20,"Graphics (hrs)":20,"Startup (hrs)":20,'
        f'"Total hrs":120,"Rate ($/hr)":{rates.get("Programming",85)},"Total $":10200,"Notes":"8 FCUs × 5 pts"}}]\n'
        f"Include rows for each system group plus: panel/hardware allowance, engineering/submittal, commissioning, project management.\n"
        f"Return ONLY the JSON array."
    )
    raw = _claude(k, prompt, 2500) or ""
    try:
        clean = raw.strip()
        if "```" in clean: clean = clean.split("```")[1]; clean = clean[4:] if clean.startswith("json") else clean
        return json.loads(clean.strip())
    except: return [{"System":"Parse error","Qty":0,"Points":0,"Engineering (hrs)":0,"Programming (hrs)":0,"Integration (hrs)":0,"Graphics (hrs)":0,"Startup (hrs)":0,"Total hrs":0,"Rate ($/hr)":0,"Total $":0,"Notes":raw[:80]}]

def ai_proposal(p, k):
    cl      = st.session_state.clients.get(p.get("client"),{}) if p.get("client") else {}
    tmpl    = cl.get("prop_template_bytes")
    equip   = p["takeoff"].get("equipment",[])
    lines   = p["estimate"].get("lines",[])
    agg     = defaultdict(int)
    for e in equip: agg[e.get("system","Unknown")]+=1
    scope   = "; ".join(f"{v}× {k}" for k,v in list(agg.items())[:15])
    try:
        total = sum(float(r.get("Total $",0)) for r in lines)*(1+p["estimate"].get("markup",10)/100)
        price = f"${total:,.0f}"
    except: price = "[TO BE DETERMINED]"
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
    return _claude(k, prompt, 3000)

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
            "AI Takeoff button reads doc names, not PDF content (use JSON upload for demo)",
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
        "Built for AI PM interview demo · "
        "West 34th Street Hotel as reference project · "
        "Honest assessment of what works, what's demo-ready, and what's next"
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

    # ── Pre-interview checklist ───────────────────────────────────────────
    st.divider()
    st.markdown("#### 📋 Pre-interview checklist")

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
        ("Practise the 5-minute demo script",
         "Overview → Discrepancies → Drawing Markup search → "
         "Send to proposal → Open this panel. Out loud, 3 times."),
        ("Have one sentence ready for every incomplete tab",
         "'This is the roadmap item — here's what it does and why the "
         "architecture supports it even though the AI piece isn't production-ready.'"),
    ]

    all_done = True
    for i, (title, desc) in enumerate(checks, 1):
        done = st.checkbox(f"**{i}. {title}**", key=f"check_{i}")
        if not done:
            all_done = False
            st.caption(f"   → {desc}")

    if all_done:
        st.success("✅ All set — you're ready for the interview.")

    # ── Demo script ───────────────────────────────────────────────────────
    st.divider()
    with st.expander("📣 5-minute demo script"):
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
    elif nav=="Clients": page_clients()
    elif nav=="Projects":page_projects()
    elif nav=="Reports": page_reports()

if __name__=="__main__":
    main()
