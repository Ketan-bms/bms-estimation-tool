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
from soo_chunker import build_chunks, coverage_report
import project_store
    print("✅ bms_analyzer_core imported successfully")
except ImportError as e:
    st.error(f"❌ Error importing bms_analyzer_core: {str(e)}")
    st.stop()

try:
    from output_generators import OutputGenerator
    print("✅ output_generators imported successfully")
except ImportError as e:
    st.error(f"❌ Error importing output_generators: {str(e)}")
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
st.markdown("Upload your SOO and controls spec → AI generates scope, point list, labor estimate, and professional proposal")

st.divider()

# ============================================================================
# SIDEBAR - API KEY & SETTINGS
# ============================================================================

@st.cache_resource
def _registry():
    """One registry shared across refreshes for the life of the process."""
    return project_store.ProjectRegistry()


registry = _registry()

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
    st.markdown('<p class="section-style">Step 2: Review structure</p>',
                unsafe_allow_html=True)

    # Read the PDF once and keep it, so the structure preview does not
    # re-parse on every widget interaction.
    file_token = f"{soo_file.name}:{soo_file.size}"
    if st.session_state.get("soo_token") != file_token:
        with st.spinner("Reading the specification..."):
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_pdf = os.path.join(tmpdir, "soo.pdf")
                with open(tmp_pdf, "wb") as f:
                    f.write(soo_file.getbuffer())
                st.session_state.soo_text = BMSAnalyzer.extract_pdf_text(
                    None, tmp_pdf
                )
        st.session_state.soo_token = file_token
        st.session_state.pop("analysis_results", None)

    soo_text = st.session_state.get("soo_text", "")
    chunks = build_chunks(soo_text)
    cov = coverage_report(soo_text, chunks)

    pages = soo_text.count("--- PAGE")
    chars = len(soo_text)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pages", pages)
    c2.metric("Characters read", f"{chars:,}")
    c3.metric("Sections found", cov["chunk_count"])
    c4.metric("Coverage", f"{cov['coverage_pct']}%")

    # Two failure modes are worth catching before any money is spent:
    # a scanned PDF with no text layer, and a layout whose headings were
    # not recognised, which degrades into unlabelled paragraph splitting.
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
            "to a heading in the document and were split by length instead. "
            "Points from those sections will cite a page range but not a "
            "named system. The specification may use a numbering style this "
            "tool does not recognise."
        )

    st.caption(
        "Deselect anything you do not want analysed. Each section is one "
        "request, so a shorter list costs less and finishes sooner."
    )

    labels = [c.label for c in chunks]
    if st.session_state.get("chunk_token") != file_token:
        st.session_state.selected_sections = labels
        st.session_state.chunk_token = file_token

    b1, b2 = st.columns(2)
    if b1.button("Select all", use_container_width=True):
        st.session_state.selected_sections = labels
    if b2.button("Clear all", use_container_width=True):
        st.session_state.selected_sections = []

    selected = st.multiselect(
        "Sections to analyse",
        options=labels,
        default=st.session_state.get("selected_sections", labels),
        key="selected_sections",
        label_visibility="collapsed",
    )

    st.dataframe(
        [
            {
                "Run": "yes" if c.label in selected else "no",
                "Section": c.label,
                "Pages": c.page_range,
                "Chars": f"{len(c.text):,}",
            }
            for c in chunks
        ],
        use_container_width=True,
        height=320,
    )

    st.markdown('<p class="section-style">Step 3: Analyze</p>',
                unsafe_allow_html=True)

    if not selected:
        st.info("Select at least one section to analyse.")
    else:
        st.caption(f"{len(selected)} of {len(chunks)} sections selected.")

    if st.button("Run Analysis", key="analyze_button",
                 use_container_width=True, disabled=not selected):

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

                analyzer = BMSAnalyzer(api_key)
                analysis_results = analyzer.run_full_analysis(
                    soo_pdf_path=soo_path,
                    spec_pdf_path=spec_path,
                    progress_callback=report,
                    section_filter=selected,
                )
                bar.progress(1.0)
                status.empty()

                st.session_state.analysis_results = analysis_results
                st.success("Analysis complete.")

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
    project_name_hint = (
        soo_file.name.rsplit(".", 1)[0] if soo_file else "BMS_Project"
    )
    
    st.markdown('<p class="section-style">📊 Step 3: Analysis Results</p>', unsafe_allow_html=True)
    
    # ===== TABS FOR RESULTS =====
    tab1, tab2, tab6, tab3, tab4, tab5 = st.tabs([
        "Scope",
        "Points",
        "Coverage",
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
            total_cost = 0
            
            for task, data in labor_breakdown.items():
                if isinstance(data, dict):
                    hours = data.get("hours", 0)
                    rate = data.get("rate", 0)
                    cost = hours * rate
                    
                    labor_data.append({
                        "Task": task.replace("_", " ").title(),
                        "Hours": hours,
                        "Rate": f"${rate}",
                        "Cost": f"${cost:,.0f}"
                    })
                    
                    total_hours += hours
                    total_cost += cost
            
            if labor_data:
                st.dataframe(labor_data, use_container_width=True)
            
            st.divider()
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Hours", total_hours)
            with col2:
                st.metric("Avg Rate", f"${total_cost/total_hours:.0f}/hr" if total_hours > 0 else "$0")
            with col3:
                st.metric("Total Cost", f"${total_cost:,.0f}")
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
        
        if not rfis.get("rfis") and not rfis.get("exclusions"):
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
            c1, c2, c3 = st.columns(3)
            c1.metric("Sections analysed", cov.get("chunk_count", 0))
            c2.metric("Document covered", f"{cov.get('coverage_pct', 0)}%")
            c3.metric("Largest section", f"{cov.get('largest_chunk', 0):,} ch")
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
