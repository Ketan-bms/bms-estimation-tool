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

st.sidebar.title("⚙️ Settings")

api_key = st.sidebar.text_input(
    "Anthropic API Key",
    type="password",
    help="Get from https://console.anthropic.com/keys"
)

# Strip whitespace/newlines. Pasted keys often carry a trailing space,
# which makes an illegal HTTP header and fails as a generic "Connection error".
api_key = api_key.strip() if api_key else ""

if not api_key:
    st.sidebar.warning("⚠️ Please enter your Anthropic API key to continue")
    st.info("**How to get API key:**\n1. Go to https://console.anthropic.com/keys\n2. Sign up or login\n3. Create new API key\n4. Paste it above")
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
    st.markdown('<p class="section-style">🔄 Step 2: Analyze</p>', unsafe_allow_html=True)
    
    if st.button("🚀 Run Analysis", key="analyze_button", use_container_width=True):
        
        # Save uploaded files temporarily
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
                
                # Show progress
                with st.spinner("Analyzing the full SOO - this runs four passes over the document..."):
                    st.write(
                        "Expect 2-5 minutes for a 50-page SOO. The full document is "
                        "sent on every pass, so longer documents take proportionally longer."
                    )
                    
                    analyzer = BMSAnalyzer(api_key)
                    analysis_results = analyzer.run_full_analysis(
                        soo_pdf_path=soo_path,
                        spec_pdf_path=spec_path
                    )
                
                st.session_state.analysis_results = analysis_results
                st.success("✅ Analysis complete!")
                
            except Exception as e:
                st.error(f"❌ Error during analysis: {str(e)}")
                st.write("Debug info:")
                st.write(f"Error type: {type(e).__name__}")
                st.write(f"Error message: {str(e)}")
                import traceback
                st.write(traceback.format_exc())

# ============================================================================
# RESULTS DISPLAY
# ============================================================================

if "analysis_results" in st.session_state:
    
    results = st.session_state.analysis_results
    
    st.markdown('<p class="section-style">📊 Step 3: Analysis Results</p>', unsafe_allow_html=True)
    
    # ===== TABS FOR RESULTS =====
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 Scope",
        "📍 Points",
        "💼 Labor",
        "⚠️ RFIs",
        "📈 Metadata"
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
        
        if points:
            st.dataframe(points, use_container_width=True, height=400)
            
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
                
                # JSON
                with col3:
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
