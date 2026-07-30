"""
streamlit_app_v2.py - PRODUCTION MVP
Streamlit interface for BMS Estimation Tool
"""

import streamlit as st
import os
import json
import tempfile
import sys
from pathlib import Path

# Import our modules
from bms_analyzer_core import BMSAnalyzer
from output_generators import OutputGenerator


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
# STYLES & LAYOUT
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
    .info-box {
        background-color: #d1ecf1;
        border-left: 5px solid #17a2b8;
        padding: 1rem;
        border-radius: 4px;
    }
    </style>
""", unsafe_allow_html=True)

# ============================================================================
# SIDEBAR - API KEY & SETTINGS
# ============================================================================

st.sidebar.title("⚙️ Settings")

api_key = st.sidebar.text_input(
    "Anthropic API Key",
    type="password",
    help="Get from https://console.anthropic.com"
)

if not api_key:
    st.sidebar.warning("⚠️ Please enter your Anthropic API key to continue")
    st.stop()

st.sidebar.divider()

# Template selection
st.sidebar.subheader("Templates")
use_template = st.sidebar.checkbox("Use proposal template", value=False)

if use_template:
    template_file = st.sidebar.file_uploader(
        "Upload Word proposal template",
        type="docx",
        help="Optional: Use your existing proposal template as base"
    )
else:
    template_file = None

st.sidebar.divider()

# Output settings
st.sidebar.subheader("Output Settings")
include_excel = st.sidebar.checkbox("Generate Excel estimate", value=True)
include_word = st.sidebar.checkbox("Generate Word proposal", value=True)

# ============================================================================
# MAIN TITLE
# ============================================================================

st.markdown(
    '<p class="header-style">🏢 BMS ESTIMATION TOOL</p>',
    unsafe_allow_html=True
)

st.markdown("**Automated BMS Estimation from SOO Documents**")
st.markdown("Upload your SOO and controls spec → AI generates scope, point list, labor estimate, and professional proposal")

st.divider()

# ============================================================================
# STEP 1: FILE UPLOAD
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
# STEP 2: ANALYZE
# ============================================================================

if soo_file:
    st.markdown('<p class="section-style">🔄 Step 2: Analyze</p>', unsafe_allow_html=True)
    
    if st.button("🚀 Run Analysis", key="analyze_button", use_container_width=True):
        
        # Save uploaded files temporarily
        with tempfile.TemporaryDirectory() as tmpdir:
            soo_path = os.path.join(tmpdir, "soo.pdf")
            with open(soo_path, "wb") as f:
                f.write(soo_file.getbuffer())
            
            spec_path = None
            if spec_file:
                spec_path = os.path.join(tmpdir, "spec.pdf")
                with open(spec_path, "wb") as f:
                    f.write(spec_file.getbuffer())
            
            try:
                # Show progress
                with st.spinner("🔄 Analyzing SOO document..."):
                    analyzer = BMSAnalyzer(api_key)
                    analysis_results = analyzer.run_full_analysis(
                        soo_pdf_path=soo_path,
                        spec_pdf_path=spec_path
                    )
                
                st.session_state.analysis_results = analysis_results
                st.success("✅ Analysis complete!")
                
            except Exception as e:
                st.error(f"❌ Error during analysis: {str(e)}")
                st.stop()

# ============================================================================
# STEP 3: DISPLAY RESULTS
# ============================================================================

if "analysis_results" in st.session_state:
    
    results = st.session_state.analysis_results
    
    st.markdown('<p class="section-style">📊 Step 3: Analysis Results</p>', unsafe_allow_html=True)
    
    # ===== TABS FOR RESULTS =====
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 Scope Overview",
        "📍 Point List",
        "💼 Labor Estimate",
        "⚠️ RFIs & Exclusions",
        "📈 Metadata"
    ])
    
    # --- TAB 1: SCOPE OVERVIEW ---
    with tab1:
        scope = results.get("scope", {})
        
        if scope:
            st.subheader("Project Overview")
            st.write(scope.get("project_overview", ""))
            
            st.subheader("Systems in Scope")
            systems = scope.get("systems_in_scope", [])
            for system in systems:
                st.write(f"✅ {system}")
            
            st.subheader("I/O Points Estimate")
            st.metric(
                "Estimated Total Points",
                scope.get("total_io_points_estimate", 0)
            )
            
            st.subheader("Integration Requirements")
            for req in scope.get("integration_requirements", []):
                st.write(f"🔗 {req}")
            
            st.subheader("Scope Clarity")
            clarity = scope.get("scope_clarity", {})
            
            col1, col2 = st.columns(2)
            
            with col1:
                if clarity.get("clearly_in_scope"):
                    st.write("✅ **Clearly In Scope:**")
                    for item in clarity["clearly_in_scope"]:
                        st.write(f"  • {item}")
            
            with col2:
                if clarity.get("needs_clarification"):
                    st.write("❓ **Needs Clarification:**")
                    for item in clarity["needs_clarification"]:
                        st.write(f"  • {item}")
    
    # --- TAB 2: POINT LIST ---
    with tab2:
        points = results.get("point_list", [])
        
        st.subheader(f"Control Point List ({len(points)} points)")
        
        if points:
            # Show as table
            st.dataframe(
                points,
                use_container_width=True,
                height=400
            )
            
            # Statistics
            col1, col2, col3, col4 = st.columns(4)
            
            ai_count = sum(1 for p in points if p.get("AI"))
            bi_count = sum(1 for p in points if p.get("BI"))
            ao_count = sum(1 for p in points if p.get("AO"))
            bo_count = sum(1 for p in points if p.get("BO"))
            
            with col1:
                st.metric("Analog Inputs (AI)", ai_count)
            with col2:
                st.metric("Binary Inputs (BI)", bi_count)
            with col3:
                st.metric("Analog Outputs (AO)", ao_count)
            with col4:
                st.metric("Binary Outputs (BO)", bo_count)
    
    # --- TAB 3: LABOR ESTIMATE ---
    with tab3:
        labor = results.get("labor_estimate", {})
        
        if labor:
            st.subheader("Labor Breakdown")
            
            labor_breakdown = labor.get("labor_estimate", {})
            
            # Create summary table
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
            
            # Display table
            st.dataframe(labor_data, use_container_width=True)
            
            st.divider()
            
            # Totals
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Hours", total_hours)
            with col2:
                st.metric("Average Rate", f"${total_cost/total_hours:.0f}/hr" if total_hours > 0 else "$0")
            with col3:
                st.metric("Total Labor Cost", f"${total_cost:,.0f}")
            
            # Assumptions
            if labor.get("assumptions"):
                st.info(f"**Assumptions:** {labor['assumptions']}")
    
    # --- TAB 4: RFIs & EXCLUSIONS ---
    with tab4:
        rfis = results.get("rfis", {})
        
        if rfis.get("rfis"):
            st.subheader("❓ Requests for Information (RFIs)")
            for i, rfi in enumerate(rfis["rfis"], 1):
                st.write(f"{i}. {rfi}")
        
        if rfis.get("exclusions"):
            st.subheader("❌ Exclusions")
            for exc in rfis["exclusions"]:
                st.write(f"• {exc}")
        
        if rfis.get("risks"):
            st.subheader("⚠️ Risk Items")
            for risk in rfis["risks"]:
                st.write(f"• {risk}")
    
    # --- TAB 5: METADATA ---
    with tab5:
        metadata = results.get("metadata", {})
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("SOO Pages", metadata.get("soo_pages", 0))
        with col2:
            st.metric("Points Extracted", metadata.get("total_points_extracted", 0))
        with col3:
            st.metric("Total I/O Count", metadata.get("total_i_o_count", 0))
    
    # ============================================================================
    # STEP 4: GENERATE OUTPUTS
    # ============================================================================
    
    st.markdown('<p class="section-style">💾 Step 4: Generate Outputs</p>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    project_name = st.text_input(
        "Project Name (for output files)",
        value=soo_file.name.split('.')[0] if soo_file else "BMS_Project",
        help="Used to name the generated files"
    )
    
    with col1:
        generate_word = st.checkbox("Generate Word Proposal", value=include_word)
    with col2:
        generate_excel = st.checkbox("Generate Excel Estimate", value=include_excel)
    with col3:
        pass  # Spacer
    
    if st.button("📥 Generate & Download All", key="generate_button", use_container_width=True):
        
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                # Prepare template path if provided
                template_path = None
                if template_file:
                    template_path = os.path.join(tmpdir, "template.docx")
                    with open(template_path, "wb") as f:
                        f.write(template_file.getbuffer())
                
                # Generate outputs
                with st.spinner("📊 Generating outputs..."):
                    generator = OutputGenerator(template_docx_path=template_path)
                    outputs = generator.export_all_outputs(
                        analysis_results=results,
                        project_name=project_name,
                        output_dir=tmpdir
                    )
                
                # Create download section
                st.success("✅ Outputs generated successfully!")
                
                st.divider()
                
                st.subheader("📥 Download Your Files")
                
                col1, col2 = st.columns(2)
                
                # Word Proposal
                if generate_word and "proposal" in outputs:
                    with open(outputs["proposal"], "rb") as f:
                        with col1:
                            st.download_button(
                                label="📄 Download Word Proposal",
                                data=f.read(),
                                file_name=f"{project_name}_Proposal.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                use_container_width=True
                            )
                
                # Excel Estimate
                if generate_excel and "estimate" in outputs:
                    with open(outputs["estimate"], "rb") as f:
                        with col2:
                            st.download_button(
                                label="📊 Download Excel Estimate",
                                data=f.read(),
                                file_name=f"{project_name}_Estimate.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )
                
                # Analysis JSON
                with col1:
                    st.download_button(
                        label="📋 Download Analysis JSON",
                        data=json.dumps(results, indent=2),
                        file_name=f"{project_name}_Analysis.json",
                        mime="application/json",
                        use_container_width=True
                    )
                
            except Exception as e:
                st.error(f"❌ Error generating outputs: {str(e)}")

# ============================================================================
# FOOTER & INFO
# ============================================================================

st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    st.info("💡 **Tips:** Upload a clear SOO PDF for best results")

with col2:
    st.info("🚀 **About:** Built with Claude AI + Python")

with col3:
    st.info("📧 **Need help?** Check the documentation")
