"""
streamlit_app_v2.py - FIXED & DEBUGGED
Streamlit interface for BMS Estimation Tool
With explicit error handling and debug output
"""

import streamlit as st
import os
import json
import tempfile
import sys
from pathlib import Path

# ============================================================================
# EXPLICIT IMPORTS WITH ERROR HANDLING
# ============================================================================

try:
    from bms_analyzer_core import BMSAnalyzer
    from output_generators import OutputGenerator
    from soo_chunker import build_chunks, coverage_report
    import project_store
    import ground_truth
except ImportError as e:
    st.error(
        f"A required module could not be imported: {e}\n\n"
        "Check that app.py, bms_analyzer_core.py, output_generators.py, "
        "soo_chunker.py and project_store.py are all present in the "
        "repository."
    )
    st.stop()

# ============================================================================
# PAGE CONFIG
# ============================================================================

st.set_page_config(
    page_title="BMS Estimation Tool",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# STYLES
# ============================================================================

st.markdown("""
    <style>
    .header-style {
        font-size: 2.5rem;
        font-weight: bold;
        color: #0066cc;
    }
    .section-style {
        font-size: 1.5rem;
        font-weight: bold;
        margin-top: 2rem;
    }
    .success-box {
        background-color: #d4edda;
        border-left: 5px solid #28a745;
        padding: 1rem;
        border-radius: 4px;
    }
    .error-box {
        background-color: #f8d7da;
        border-left: 5px solid #f5c6cb;
        padding: 1rem;
        border-radius: 4px;
    }
    </style>
""", unsafe_allow_html=True)

# ============================================================================
# TITLE
# ============================================================================

st.markdown(
    '<p class="header-style">🏢 BMS ESTIMATION TOOL</p>',
    unsafe_allow_html=True
)

st.markdown("**Automated BMS Estimation from SOO Documents**")

if len(registry):
    with st.expander(f"📊 Projects dashboard ({len(registry)} saved)",
                     expanded=True):
        render_project_cards(registry, key_prefix="dash")
    st.divider()
st.markdown("Upload your SOO and controls spec → AI generates scope, point list, labor estimate, and professional proposal")

st.divider()

# ============================================================================
# SIDEBAR - API KEY & SETTINGS
# ============================================================================

@st.cache_resource
def _extraction_cache():
    """Section extractions already paid for, reused across runs."""
    return {}


@st.cache_resource
def _registry():
    """One registry shared across refreshes for the life of the process."""
    return project_store.ProjectRegistry()


registry = _registry()
extraction_cache = _extraction_cache()

def render_project_cards(registry, key_prefix):
    """Zoho-Projects-style cards: status pill, coverage bar, key metrics.

    Pure Streamlit layout over data already computed during analysis - no
    API calls, so this costs nothing to render or to look at repeatedly.
    """
    names = registry.names()
    if not names:
        st.caption("No saved projects yet.")
        return

    per_row = 3
    for row_start in range(0, len(names), per_row):
        cols = st.columns(per_row)
        for col, name in zip(cols, names[row_start:row_start + per_row]):
            record = registry.get(name)
            if not record:
                continue
            summary = record.get("summary", {}) or {}
            status_label, status_emoji = project_store.project_status(summary)

            with col:
                with st.container(border=True):
                    st.markdown(f"**{name}**")
                    st.caption(
                        f"{record.get('source_file', '') or 'imported'} · "
                        f"saved {record.get('saved_at', '')}"
                    )
                    st.markdown(f"{status_emoji} {status_label}")

                    coverage = summary.get("coverage_pct")
                    if coverage is not None:
                        st.progress(min(max(coverage / 100, 0.0), 1.0),
                                   text=f"Coverage {coverage}%")

                    m1, m2, m3 = st.columns(3)
                    m1.metric("Points", summary.get("points", 0))
                    m2.metric("I/O", summary.get("io_count", 0))
                    m3.metric("Pages", summary.get("pages", 0))

                    conf = summary.get("confidence_counts") or {}
                    if conf:
                        st.caption(
                            f"Confidence: high {conf.get('high', 0)} · "
                            f"medium {conf.get('medium', 0)} · "
                            f"low {conf.get('low', 0)}"
                        )

                    b1, b2, b3 = st.columns(3)
                    if b1.button("Open", key=f"{key_prefix}_open_{name}",
                                use_container_width=True):
                        st.session_state.analysis_results = record["analysis"]
                        st.session_state.loaded_project = name
                        st.rerun()
                    b2.download_button(
                        "Export", data=project_store.to_json(record),
                        file_name=project_store.export_filename(name),
                        mime="application/json",
                        key=f"{key_prefix}_export_{name}",
                        use_container_width=True,
                    )
                    if b3.button("Delete", key=f"{key_prefix}_delete_{name}",
                                use_container_width=True):
                        registry.delete(name)
                        st.rerun()



# ---- Projects ----
st.sidebar.title("Projects")

if len(registry):
    st.sidebar.caption(f"{len(registry)} project(s) held in this session")
    choice = st.sidebar.selectbox(
        "Open a saved project",
        ["-"] + registry.names(),
        key="project_choice",
    )
    if choice != "-" and st.sidebar.button("Load", use_container_width=True):
        record = registry.get(choice)
        if record:
            st.session_state.analysis_results = record["analysis"]
            st.session_state.loaded_project = choice
            st.rerun()
else:
    st.sidebar.caption("No saved projects yet in this session.")

uploaded_project = st.sidebar.file_uploader(
    "Open a project file", type="json", key="project_import"
)
if uploaded_project is not None:
    try:
        record = project_store.from_json(uploaded_project.getvalue().decode("utf-8"))
        registry.save(record)
        st.session_state.analysis_results = record["analysis"]
        st.session_state.loaded_project = record["project_name"]
        st.sidebar.success(f"Opened {record['project_name']}")
    except ValueError as e:
        st.sidebar.error(str(e))

st.sidebar.info(
    "Saved projects live in this app's memory and are lost when the app "
    "restarts or sleeps. Export a project file to keep it."
)

st.sidebar.divider()
st.sidebar.title("⚙️ Settings")


def _stored_api_key():
    """Read the key from Streamlit secrets, if one has been configured.

    st.secrets raises when no secrets are configured at all (local runs,
    fresh deploys), so this must not be allowed to crash the app.
    """
    try:
        return str(st.secrets.get("ANTHROPIC_API_KEY", "")).strip()
    except Exception:
        return ""


api_key = _stored_api_key()

if api_key:
    st.sidebar.success("API key loaded from app settings")
else:
    api_key = st.sidebar.text_input(
        "Anthropic API Key",
        type="password",
        help="Get from https://console.anthropic.com/keys",
    )
    # Pasted keys often carry a trailing space, which makes an illegal HTTP
    # header and fails as an opaque "Connection error".
    api_key = api_key.strip() if api_key else ""

if not api_key:
    st.sidebar.warning("Enter your Anthropic API key to continue")
    st.info(
        "**To avoid entering the key each time:** in Streamlit Cloud open "
        "Manage app -> Settings -> Secrets and add a line reading "
        "`ANTHROPIC_API_KEY = \"sk-ant-...\"`, then reboot the app."
    )
    st.stop()

st.sidebar.divider()
st.sidebar.subheader("Cost")

# Per-million-token input/output rates, checked 2026-07-30. Sonnet 5's rate
# is introductory through 2026-08-31; verify at anthropic.com/pricing after
# that date, since it reverts to a higher standard rate.
MODEL_RATES = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
}
EXTRACTION_CHOICES = {
    "Haiku 4.5 - cheapest ($1/$5 per MTok)": "claude-haiku-4-5-20251001",
    "Sonnet 5 - balanced ($2/$10 per MTok)": "claude-sonnet-5",
    "Opus 5 - most capable ($5/$25 per MTok)": "claude-opus-5",
}
extraction_label = st.sidebar.selectbox(
    "Model for point extraction",
    list(EXTRACTION_CHOICES),
    index=0,
    help="Extraction transcribes points already written in the text and is "
         "the bulk of the requests. Scope, labour and RFI analysis always "
         "use Opus 5, but that is only 3 requests regardless of document size.",
)
extraction_model = EXTRACTION_CHOICES[extraction_label]
extraction_rate = MODEL_RATES[extraction_model]

OVERVIEW_CHOICES = {
    "Haiku 4.5 - cheapest ($1/$5 per MTok)": "claude-haiku-4-5-20251001",
    "Sonnet 5 - balanced ($2/$10 per MTok)": "claude-sonnet-5",
    "Opus 5 - most capable ($5/$25 per MTok)": "claude-opus-5",
}
overview_label = st.sidebar.selectbox(
    "Model for scope / labour / RFI analysis",
    list(OVERVIEW_CHOICES),
    index=0,
    help="Defaults to the cheapest tier for MVP use. This is the one call "
         "that reads the whole document, so a weak model here can produce a "
         "generic labour estimate or miss a real ambiguity. If the RFIs tab "
         "reads as vague boilerplate rather than specific to this document, "
         "move this one dropdown to Sonnet - it is a single request, so the "
         "cost difference per run is small even though the per-token rate "
         "is not.",
)
overview_model = OVERVIEW_CHOICES[overview_label]
overview_rate = MODEL_RATES[overview_model]

if len(extraction_cache):
    st.sidebar.caption(f"{len(extraction_cache)} section(s) cached - free to re-run")
    if st.sidebar.button("Clear cache", use_container_width=True):
        extraction_cache.clear()
        st.rerun()

budget = st.sidebar.number_input(
    "Remaining balance ($)", min_value=0.0, value=20.0, step=1.0,
    help="What you have left in the Anthropic console. Used only to warn "
         "you here - it does not touch billing.",
)
spent = st.session_state.get("session_spend_usd", 0.0)
remaining = budget - spent
st.sidebar.metric("Spent this session (est.)", f"${spent:.2f}",
                  delta=f"${remaining:.2f} left" if remaining >= 0 else
                        f"${-remaining:.2f} over", delta_color="off")
if remaining < 1.0:
    st.sidebar.error(
        "Under $1 estimated remaining. A live run could fail mid-way if the "
        "actual balance runs out. Load a saved project instead of running "
        "the API again."
    )

st.sidebar.divider()
st.sidebar.subheader("Demo mode")
demo_lock = st.sidebar.checkbox(
    "Lock: no new API calls",
    help="For presenting live. Disables Run Analysis so nothing can spend "
         "money or fail on a network problem in front of an audience. "
         "Loading a saved or cached project still works.",
)
if demo_lock:
    st.sidebar.success(
        "Locked. Only saved/cached results can be shown - nothing here can "
        "call the API or spend money."
    )

st.sidebar.divider()

# Template selection
st.sidebar.subheader("Templates")
use_template = st.sidebar.checkbox("Use proposal template (optional)", value=False)

template_file = None
if use_template:
    template_file = st.sidebar.file_uploader(
        "Upload Word proposal template",
        type="docx",
        help="Optional: Use your existing proposal template as base"
    )

st.sidebar.divider()

# Output settings
st.sidebar.subheader("Output Settings")
include_excel = st.sidebar.checkbox("Generate Excel estimate", value=True)
include_word = st.sidebar.checkbox("Generate Word proposal", value=True)

# ============================================================================
# MAIN: FILE UPLOAD
# ============================================================================

st.markdown('<p class="section-style">📋 Step 1: Upload Documents</p>', unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    soo_file = st.file_uploader(
        "Upload SOO (Sequence of Operations) PDF",
        type="pdf",
        help="Your Sequence of Operations document"
    )

with col2:
    spec_file = st.file_uploader(
        "Upload HVAC Controls Spec PDF (optional)",
        type="pdf",
        help="Optional: HVAC controls specification document"
    )

# ============================================================================
# ANALYZE
# ============================================================================

if soo_file:
    st.markdown('<p class="section-style">Step 2: Analyze</p>',
                unsafe_allow_html=True)

    # Read the PDF once and hold it, so the summary does not re-parse on
    # every widget interaction.
    file_token = f"{soo_file.name}:{soo_file.size}"
    if st.session_state.get("soo_token") != file_token:
        with st.spinner("Reading the specification..."):
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_pdf = os.path.join(tmpdir, "soo.pdf")
                with open(tmp_pdf, "wb") as f:
                    f.write(soo_file.getbuffer())
                st.session_state.soo_text = BMSAnalyzer.extract_pdf_text(tmp_pdf)
        st.session_state.soo_token = file_token
        st.session_state.pop("analysis_results", None)
        st.session_state.pop("section_override", None)

    soo_text = st.session_state.get("soo_text", "")
    chunks = build_chunks(soo_text)
    cov = coverage_report(soo_text, chunks)
    labels = [c.label for c in chunks]

    pages = soo_text.count("--- PAGE")
    chars = len(soo_text)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pages", pages)
    c2.metric("Characters read", f"{chars:,}")
    c3.metric("Systems found", cov["chunk_count"])
    c4.metric("Coverage", f"{cov['coverage_pct']}%")

    # Surfaced without asking the user to act: a scanned PDF cannot be read
    # at all, and unrecognised headings mean weaker provenance. Both change
    # how far the results should be trusted.
    if pages and chars / pages < 200:
        st.error(
            f"Only {chars:,} characters across {pages} pages. This PDF is "
            "probably scanned images rather than text, and cannot be read "
            "without OCR. Analysing it will produce little or nothing."
        )

    unlabelled = [c for c in chunks if "part " in c.title.lower()]
    if chunks and len(unlabelled) > len(chunks) / 2:
        st.warning(
            f"{len(unlabelled)} of {len(chunks)} sections could not be matched "
            "to a heading and were split by length instead. Their points will "
            "cite a page range but not a named system."
        )

    # The whole document is analysed by default. Administrative sections
    # (Related Documents, Summary, Definitions) are dropped automatically
    # because they contain no control points.
    override = st.session_state.get("section_override")
    selected = override if override is not None else labels

    with st.expander(
        f"Systems detected ({len(chunks)})"
        + ("" if override is None else f" - limited to {len(selected)}")
    ):
        st.dataframe(
            [
                {
                    "System": c.label,
                    "Pages": c.page_range,
                    "Size": f"{len(c.text):,} ch",
                }
                for c in chunks
            ],
            use_container_width=True,
            height=300,
        )

        limit = st.checkbox(
            "Analyse only part of this document",
            value=override is not None,
            help="Useful for a quick check on a long specification before "
                 "running the whole thing.",
        )
        if limit:
            picked = st.multiselect(
                "Systems to analyse",
                options=labels,
                default=selected,
            )
            st.session_state.section_override = picked
            selected = picked
        else:
            st.session_state.section_override = None
            selected = labels

    if not selected:
        st.info("Select at least one system, or untick the limit to analyse all.")
    else:
        chosen = [c for c in chunks if c.label in selected]

        # Sections already extracted at this prompt version and model cost
        # nothing to repeat, so exclude them from the estimate.
        probe = BMSAnalyzer.__new__(BMSAnalyzer)
        probe.EXTRACTION_MODEL = extraction_model
        billable = [c for c in chosen
                    if probe._cache_key(c) not in extraction_cache]
        cached_n = len(chosen) - len(billable)

        # Roughly four characters per token: enough to size a run.
        in_tokens = sum(len(c.text) for c in billable) // 4 + len(billable) * 250

        overview_in_tokens = len(soo_text) // 4
        est_cost = (
            in_tokens / 1_000_000 * extraction_rate[0]
            + overview_in_tokens / 1_000_000 * overview_rate[0]
        )
        msg = (
            f"{len(billable)} extraction request(s) plus 1 combined analysis "
            f"request, about {in_tokens + overview_in_tokens:,} input tokens, "
            f"roughly ${est_cost:.2f}."
        )
        if cached_n:
            msg += f" {cached_n} section(s) already cached and free."
        st.caption(msg)

        if demo_lock:
            st.warning(
                "Demo mode is locked in the sidebar. Turn it off to run the "
                "API, or load a saved project instead."
            )

    if st.button("Run Analysis", key="analyze_button",
                 use_container_width=True,
                 disabled=(not selected) or demo_lock):
        if demo_lock:
            st.stop()

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                soo_path = os.path.join(tmpdir, "soo.pdf")
                with open(soo_path, "wb") as f:
                    f.write(soo_file.getbuffer())

                spec_path = None
                if spec_file:
                    spec_path = os.path.join(tmpdir, "spec.pdf")
                    with open(spec_path, "wb") as f:
                        f.write(spec_file.getbuffer())

                bar = st.progress(0.0)
                status = st.empty()

                def report(done, total, label):
                    if total:
                        bar.progress(min(done / total, 1.0))
                        status.write(f"Section {done + 1} of {total}: {label}")
                    else:
                        status.write(label)

                analyzer = BMSAnalyzer(
                    api_key,
                    cache=extraction_cache,
                    extraction_model=extraction_model,
                    overview_model=overview_model,
                )
                analysis_results = analyzer.run_full_analysis(
                    soo_pdf_path=soo_path,
                    spec_pdf_path=spec_path,
                    progress_callback=report,
                    section_filter=selected,
                )
                bar.progress(1.0)
                status.empty()

                usage = analysis_results.get("metadata", {}).get("usage", {})
                ex = usage.get("extraction", {})
                ov = usage.get("overview", {})
                run_cost = (
                    ex.get("input_tokens", 0) / 1_000_000 * extraction_rate[0]
                    + ex.get("output_tokens", 0) / 1_000_000 * extraction_rate[1]
                    + ov.get("input_tokens", 0) / 1_000_000 * overview_rate[0]
                    + ov.get("output_tokens", 0) / 1_000_000 * overview_rate[1]
                )
                st.session_state.session_spend_usd = (
                    st.session_state.get("session_spend_usd", 0.0) + run_cost
                )

                total_in = ex.get("input_tokens", 0) + ov.get("input_tokens", 0)
                total_out = ex.get("output_tokens", 0) + ov.get("output_tokens", 0)
                st.session_state.analysis_results = analysis_results
                st.success(
                    f"Analysis complete. This run used {total_in:,} input and "
                    f"{total_out:,} output tokens, about ${run_cost:.2f}."
                )

            except Exception as e:
                st.error(f"Error during analysis: {e}")
                st.write(f"Error type: {type(e).__name__}")
                import traceback
                st.write(traceback.format_exc())

# ============================================================================
# RESULTS DISPLAY
# ============================================================================

if "analysis_results" in st.session_state:
    
    results = st.session_state.analysis_results

    st.markdown('<p class="section-style">Project</p>', unsafe_allow_html=True)
    pc1, pc2 = st.columns([2, 1])
    default_name = st.session_state.get(
        "loaded_project",
        soo_file.name.rsplit(".", 1)[0] if soo_file else "Untitled project",
    )
    project_label = pc1.text_input("Project name", value=default_name,
                                   key="project_label")

    record = project_store.make_record(
        project_label,
        soo_file.name if soo_file else st.session_state.get("loaded_project", ""),
        results,
    )

    if pc2.button("Save to session", use_container_width=True):
        registry.save(record)
        st.session_state.loaded_project = project_label
        st.success(f"Saved '{project_label}'. Export it to keep it permanently.")

    st.download_button(
        "Export project file",
        data=project_store.to_json(record),
        file_name=project_store.export_filename(project_label),
        mime="application/json",
        help="A portable copy of this analysis. Re-open it from the sidebar.",
    )

    if len(registry):
        with st.expander(f"Projects in this session ({len(registry)})",
                         expanded=False):
            render_project_cards(registry, key_prefix="results")

    st.divider()

    project_name_hint = project_label or "BMS_Project"
    
    st.markdown('<p class="section-style">📊 Step 3: Analysis Results</p>', unsafe_allow_html=True)
    
    # ===== TABS FOR RESULTS =====
    tab1, tab2, tab6, tab7, tab3, tab4, tab5 = st.tabs([
        "Scope",
        "Points",
        "Coverage",
        "Accuracy",
        "Labor",
        "RFIs",
        "Metadata",
    ])
    
    # --- TAB 1: SCOPE ---
    with tab1:
        scope = results.get("scope", {})
        
        if scope:
            st.subheader("Project Overview")
            st.write(scope.get("project_overview", "No overview available"))
            
            st.subheader("Systems in Scope")
            systems = scope.get("systems_in_scope", [])
            if systems:
                for system in systems:
                    st.write(f"✅ {system}")
            
            st.metric("Estimated I/O Points", scope.get("total_io_points_estimate", 0))
            
            st.subheader("Integration Requirements")
            for req in scope.get("integration_requirements", []):
                st.write(f"🔗 {req}")
        else:
            st.info("No scope data available")
    
    # --- TAB 2: POINT LIST ---
    with tab2:
        points = results.get("point_list", [])
        
        st.subheader(f"Control Point List ({len(points)} points)")

        if results.get("metadata", {}).get("point_list_truncated"):
            st.warning(
                "**At least one section hit its response limit** and was "
                "salvaged partially. Check the Coverage tab to see which, and "
                "treat that section's points as incomplete."
            )

        if points:
            conf_counts = results.get("metadata", {}).get("confidence_counts", {})
            if conf_counts:
                c1, c2, c3 = st.columns(3)
                c1.metric("High confidence", conf_counts.get("high", 0),
                          help="Tag and evidence both found verbatim in the source section")
                c2.metric("Medium", conf_counts.get("medium", 0),
                          help="Tag verbatim, but the evidence phrase could not be matched")
                c3.metric("Low", conf_counts.get("low", 0),
                          help="Tag not found in source, ambiguous I/O type, or repeated across sections")

            levels = st.multiselect(
                "Show confidence levels",
                ["high", "medium", "low"],
                default=["high", "medium", "low"],
            )
            shown = [p for p in points if p.get("Confidence", "low") in levels]
            st.caption(f"Showing {len(shown)} of {len(points)} points")
            st.dataframe(shown, use_container_width=True, height=400)

            # Export the filtered view, so a reviewer can pull just the
            # high-confidence rows if that is what they want to work from.
            export_filtered = len(shown) != len(points)
            try:
                import io as _io
                import tempfile as _tf

                subset = dict(results)
                subset["point_list"] = shown if export_filtered else points

                with _tf.TemporaryDirectory() as _d:
                    _path = os.path.join(_d, "points.xlsx")
                    OutputGenerator().generate_point_list_excel(
                        subset,
                        project_name_hint,
                        _path,
                    )
                    with open(_path, "rb") as _f:
                        _data = _f.read()

                label = (
                    f"Download point list ({len(shown)} filtered rows)"
                    if export_filtered
                    else f"Download point list ({len(points)} rows)"
                )
                st.download_button(
                    label=label,
                    data=_data,
                    file_name=f"{project_name_hint}_Point_List.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            except Exception as e:
                st.error(f"Could not build the point list workbook: {e}")

            col1, col2, col3, col4 = st.columns(4)
            ai_count = sum(1 for p in points if p.get("AI"))
            bi_count = sum(1 for p in points if p.get("BI"))
            ao_count = sum(1 for p in points if p.get("AO"))
            bo_count = sum(1 for p in points if p.get("BO"))
            
            with col1:
                st.metric("AI", ai_count)
            with col2:
                st.metric("BI", bi_count)
            with col3:
                st.metric("AO", ao_count)
            with col4:
                st.metric("BO", bo_count)
        else:
            st.info("No points extracted")
    
    # --- TAB 3: LABOR ---
    with tab3:
        labor = results.get("labor_estimate", {})
        
        if labor:
            labor_breakdown = labor.get("labor_estimate", {})
            labor_data = []
            total_hours = 0
            
            for task, data in labor_breakdown.items():
                if isinstance(data, dict):
                    hours = data.get("hours", 0) or 0
                    try:
                        hours = float(hours)
                    except (TypeError, ValueError):
                        hours = 0
                    
                    labor_data.append({
                        "Task": task.replace("_", " ").title(),
                        "Hours": hours,
                    })
                    total_hours += hours
            
            if labor_data:
                st.dataframe(labor_data, use_container_width=True)
            
            st.divider()
            st.metric("Total Hours", f"{total_hours:,.0f}")
            st.caption(
                "Hours only. Rates and cost are a separate business decision "
                "applied outside this tool, not part of the AI-generated estimate."
            )
        else:
            st.info("No labor estimate available")
    
    # --- TAB 4: RFIs ---
    with tab4:
        rfis = results.get("rfis", {})
        
        if rfis.get("rfis"):
            st.subheader("❓ RFIs")
            for i, rfi in enumerate(rfis["rfis"], 1):
                st.write(f"{i}. {rfi}")
        
        if rfis.get("exclusions"):
            st.subheader("❌ Exclusions")
            for exc in rfis["exclusions"]:
                st.write(f"• {exc}")

        spec_check = results.get("spec_cross_check")
        if spec_check is not None:
            devices = spec_check.get("devices_without_sequence", [])
            st.subheader("🔍 Controls Spec Cross-Check")
            st.caption(
                "Equipment named in the uploaded controls spec with no "
                "matching point in the SOO extraction - a device that may "
                "be scheduled with no stated control sequence."
            )
            if devices:
                for d in devices:
                    st.write(f"• {d}")
            else:
                st.write("No unmatched equipment found.")

        if not rfis.get("rfis") and not rfis.get("exclusions") and not spec_check:
            st.info("No RFIs or exclusions identified")
    
    # --- TAB 6: COVERAGE ---
    with tab6:
        meta = results.get("metadata", {})
        cov = meta.get("coverage", {})
        sections = meta.get("sections", [])
        failed = meta.get("sections_failed", [])

        st.subheader("What was actually analysed")
        st.caption(
            "Every point traces back to one section below. Anything not listed "
            "here was not read, so gaps are visible rather than assumed."
        )

        if cov:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Sections analysed", cov.get("chunk_count", 0))
            c2.metric("Document covered", f"{cov.get('coverage_pct', 0)}%")
            c3.metric("Largest section", f"{cov.get('largest_chunk', 0):,} ch")
            c4.metric("Reused from cache", meta.get("sections_cached", 0),
                      help="Sections whose text was unchanged since a previous "
                           "run, so no request was made for them.")
            st.caption(
                "Coverage below 100% is expected: administrative sections such as "
                "Related Documents, Summary and Definitions contain no control "
                "points and are skipped deliberately."
            )

        if failed:
            st.error(
                f"{len(failed)} section(s) failed and contributed no points. "
                "The totals below are incomplete until these are re-run."
            )
            for f in failed:
                st.write(f"**{f['section']}** (p{f['pages']}) - {f['detail']}")

        if sections:
            st.dataframe(
                [
                    {
                        "Section": r["section"],
                        "Pages": r["pages"],
                        "Chars": f"{r['chars']:,}",
                        "Points": r["points"],
                        "Status": r["status"],
                    }
                    for r in sections
                ],
                use_container_width=True,
                height=420,
            )

            empty = [r for r in sections if r["status"] == "ok" and r["points"] == 0]
            if empty:
                st.info(
                    f"{len(empty)} section(s) returned zero points. That is often "
                    "correct for narrative sections, but worth a glance: "
                    + ", ".join(r["section"][:40] for r in empty[:5])
                )

    # --- TAB 7: ACCURACY (vs. ground truth) ---
    with tab7:
        st.subheader("Compare against an engineer's point list")
        st.caption(
            "Coverage tells you how much of the document was read. This "
            "tells you whether the extracted points are actually correct, "
            "by matching them against a real point matrix - typically "
            "produced by the mechanical/controls engineer for the same "
            "project. Matching is done by wording similarity, so it is not "
            "perfect: read the borderline matches yourself before trusting "
            "them."
        )

        gt_file = st.file_uploader(
            "Upload the ground-truth point matrix (PDF)",
            type="pdf",
            key="ground_truth_upload",
            help="A table-format point list: System, Point Description, "
                 "I/O columns, Notes - the kind an engineer issues alongside "
                 "the SOO."
        )

        if gt_file is not None:
            if st.button("Run comparison", key="run_gt_compare"):
                with tempfile.TemporaryDirectory() as tmpdir:
                    gt_path = os.path.join(tmpdir, "ground_truth.pdf")
                    with open(gt_path, "wb") as f:
                        f.write(gt_file.getbuffer())

                    try:
                        with st.spinner("Parsing ground-truth table..."):
                            gt_points = ground_truth.parse_point_matrix(gt_path)
                        st.session_state.gt_comparison = ground_truth.compare(
                            results.get("point_list", []), gt_points
                        )
                        st.session_state.gt_point_count = len(gt_points)
                    except ValueError as e:
                        st.error(str(e))
                        st.session_state.pop("gt_comparison", None)

        if "gt_comparison" in st.session_state:
            r = st.session_state.gt_comparison

            st.divider()
            c1, c2, c3 = st.columns(3)
            c1.metric("Ground-truth points", r["n_ground_truth"])
            c2.metric("Extracted points", r["n_extracted"])
            c3.metric("Matched", r["n_matched"],
                     help=f"{r['n_confident']} confident, {r['n_borderline']} borderline")

            c4, c5 = st.columns(2)
            c4.metric("Recall (confident matches only)",
                      f"{r['recall_confident']:.1%}",
                      help="Share of ground-truth points found with a strong "
                           "wording match. The conservative number.")
            c5.metric("Recall (all matches)", f"{r['recall_all']:.1%}",
                      help="Includes borderline matches - wording overlap "
                           "that may or may not be the same point. The "
                           "optimistic number.")

            if r["n_borderline"] > r["n_confident"]:
                st.warning(
                    "More borderline matches than confident ones - the gap "
                    "between the two recall numbers above is real. Spot-check "
                    "the borderline matches before quoting either figure."
                )

            with st.expander(f"Missed ground-truth points ({len(r['missed'])})"):
                st.caption("In the ground truth, no corresponding extracted point found.")
                if r["missed"]:
                    st.dataframe(
                        [{"System": m["system"], "Point": m["point_description"],
                          "Page": m["page"]} for m in r["missed"]],
                        use_container_width=True, height=300,
                    )
                else:
                    st.write("None.")

            with st.expander(f"Borderline matches ({r['n_borderline']}) - verify these"):
                st.caption(
                    "Wording similarity crossed the threshold but not the "
                    "confident bar. Some are real matches in different words; "
                    "some share vocabulary without being the same point."
                )
                borderline = [m for m in r["matches"] if m["tier"] == "borderline"]
                if borderline:
                    st.dataframe(
                        [{"Ground truth": m["ground_truth"]["point_description"],
                          "Extracted": m["extracted"].get("Point_Name", ""),
                          "Similarity": m["similarity"]} for m in borderline],
                        use_container_width=True, height=250,
                    )
                else:
                    st.write("None.")

            with st.expander(f"Extra extracted points ({len(r['extra'])})"):
                st.caption(
                    "In the extraction, no corresponding ground-truth point "
                    "found. Not necessarily wrong - could be different "
                    "terminology, or a genuine point the ground truth omits."
                )
                if r["extra"]:
                    st.dataframe(
                        [{"Equipment": e.get("Equipment", ""),
                          "Point": e.get("Point_Name", ""),
                          "Confidence": e.get("Confidence", "")} for e in r["extra"]],
                        use_container_width=True, height=250,
                    )
                else:
                    st.write("None.")

    # --- TAB 5: METADATA ---
    with tab5:
        metadata = results.get("metadata", {})
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("SOO Pages", metadata.get("soo_pages", 0))
        with col2:
            st.metric("Characters Read", f"{metadata.get('soo_characters', 0):,}")
        with col3:
            st.metric("Points Extracted", metadata.get("total_points_extracted", 0))
        with col4:
            st.metric("Total I/O Count", metadata.get("total_i_o_count", 0))

        pages = metadata.get("soo_pages", 0)
        chars = metadata.get("soo_characters", 0)
        if pages and chars / pages < 200:
            st.warning(
                f"Only {chars:,} characters across {pages} pages "
                f"({chars // pages:,} per page). That is very low for a text "
                "SOO - the PDF may be scanned images rather than a text layer, "
                "in which case PyMuPDF cannot read it and OCR would be needed."
            )
    
    # ===== GENERATE OUTPUTS =====
    
    st.markdown('<p class="section-style">💾 Step 4: Generate Outputs</p>', unsafe_allow_html=True)
    
    project_name = st.text_input(
        "Project Name (for file names)",
        value=soo_file.name.split('.')[0] if soo_file else "BMS_Project"
    )
    
    col1, col2 = st.columns(2)
    with col1:
        generate_word = st.checkbox("Generate Word Proposal", value=include_word)
    with col2:
        generate_excel = st.checkbox("Generate Excel Estimate", value=include_excel)
    
    if st.button("📥 Generate & Download All", key="generate_button", use_container_width=True):
        
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                template_path = None
                if template_file:
                    template_path = os.path.join(tmpdir, "template.docx")
                    with open(template_path, "wb") as f:
                        f.write(template_file.getbuffer())
                
                with st.spinner("📊 Generating outputs..."):
                    generator = OutputGenerator(template_docx_path=template_path)
                    outputs = generator.export_all_outputs(
                        analysis_results=results,
                        project_name=project_name,
                        output_dir=tmpdir
                    )
                
                st.success("✅ Outputs generated!")
                st.divider()
                
                st.subheader("📥 Download Your Files")
                
                col1, col2, col3 = st.columns(3)
                
                # Word
                if generate_word and "proposal" in outputs:
                    with open(outputs["proposal"], "rb") as f:
                        with col1:
                            st.download_button(
                                label="📄 Word Proposal",
                                data=f.read(),
                                file_name=f"{project_name}_Proposal.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                use_container_width=True
                            )
                
                # Excel
                if generate_excel and "estimate" in outputs:
                    with open(outputs["estimate"], "rb") as f:
                        with col2:
                            st.download_button(
                                label="📊 Excel Estimate",
                                data=f.read(),
                                file_name=f"{project_name}_Estimate.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )
                
                # Standalone point list
                pl_path = os.path.join(tmpdir, f"{project_name}_Point_List.xlsx")
                OutputGenerator().generate_point_list_excel(
                    results, project_name, pl_path
                )
                with open(pl_path, "rb") as f:
                    with col3:
                        st.download_button(
                            label="Point List (Excel)",
                            data=f.read(),
                            file_name=f"{project_name}_Point_List.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                        )

                # JSON
                with col1:
                    st.download_button(
                        label="📋 JSON Analysis",
                        data=json.dumps(results, indent=2),
                        file_name=f"{project_name}_Analysis.json",
                        mime="application/json",
                        use_container_width=True
                    )
                
            except Exception as e:
                st.error(f"❌ Error generating outputs: {str(e)}")
                st.write("Debug info:")
                st.write(f"Error type: {type(e).__name__}")
                st.write(f"Error message: {str(e)}")
                import traceback
                st.write(traceback.format_exc())

# ============================================================================
# FOOTER
# ============================================================================

st.divider()

col1, col2, col3 = st.columns(3)
with col1:
    st.info("💡 Upload clear SOO PDFs for best results")
with col2:
    st.info("🚀 Powered by Claude AI")
with col3:
    st.info("📧 v1.0 - Production Ready")
