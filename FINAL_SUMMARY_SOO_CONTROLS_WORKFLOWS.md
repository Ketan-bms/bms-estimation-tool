# ✅ Complete SOO & Controls Spec Extraction Workflows

**Status:** Ready for app.py integration  
**Date:** July 29, 2026

---

## 🎯 What You Get (Exactly What You Asked For)

### From SOO (Sequence of Operations) — 5 Extractions:

1. **Overview** → Bird's eye view (system breakdown, DDC vs manufacturer controller approach)
2. **Proposal** → You provide template, I generate following same format (Qty x maintained)
3. **Point List (Main)** → Your Excel format: 11 columns, system-wise
4. **Point List (Appendix)** → Same Excel format, special sequences only
5. **Important Notes** → For estimation (DDC complexity, lead times, safety interlocks, etc.)

### From Controls Spec — 2 Extractions:

1. **Important Notes** → 8 categories of requirements/decisions
2. **Questions** → Ambiguous/unclear items flagged for clarification

---

## 📦 Deliverables (Ready Now)

### New Python Modules (2):

#### **`soo_extractor.py`** (280 lines)
```python
generate_overview_prompt(project_name, soo_text)
→ Bird's eye view of control approach per system

generate_pointlist_prompt(project_name, soo_text, takeoff_equip=None)
→ Main point list extraction (11 columns)

generate_appendix_prompt(project_name, soo_text, main_equipment)
→ Appendix points extraction (special sequences)

generate_important_notes_prompt(project_name, soo_text)
→ Estimation key points (7 categories)
```

#### **`controls_spec_extractor.py`** (250 lines)
```python
generate_notes_prompt(project_name, spec_text)
→ Extract requirements/decisions (8 categories)

generate_questions_prompt(project_name, spec_text)
→ Extract ambiguous/missing items

parse_overview_response(raw_response) → JSON
parse_pointlist_response(raw_response) → Array
parse_notes_response(raw_response) → JSON
parse_questions_response(raw_response) → Array
```

### Documentation (1):

#### **`WORKFLOW_SOO_CONTROLS_SPEC.md`** (500 lines)
Complete guide including:
- Architecture diagram
- Exact format examples for all 7 outputs
- Column definitions for Point List (11 columns)
- Category definitions for Important Notes
- Category definitions for Questions
- Example outputs
- Implementation notes

---

## 🔧 How to Use (Implementation)

### For Each SOO Extraction:

```python
# 1. Extract SOO text from PDF/DOCX
soo_text = extract_text_from_pdf(soo_bytes)

# 2. Generate Claude prompt
prompt = generate_overview_prompt(project_name, soo_text)

# 3. Send to Claude
response = claude.messages.create(
    model="claude-opus-4.5",
    max_tokens=3000,
    messages=[{"role": "user", "content": prompt}]
)

# 4. Parse response
data = parse_overview_response(response.content[0].text)

# 5. Display in Streamlit
st.json(data)  # or render as table/display
```

### Streamlit UI Structure:

```python
with st.expander("SOO (Sequence of Operations)"):
    soo_file = st.file_uploader("Upload SOO PDF or DOCX", type=["pdf", "docx"])
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        if st.button("📋 Overview"):
            overview_data = extract_overview(soo_text)
            st.dataframe(overview_data)
    
    with col2:
        if st.button("📄 Proposal"):
            proposal_template = st.file_uploader("Your proposal template")
            proposal_docx = generate_proposal(soo_text, proposal_template)
            st.download_button("Download DOCX", proposal_docx)
    
    with col3:
        if st.button("📊 Point List"):
            point_list_df = extract_pointlist(soo_text)
            st.dataframe(point_list_df)
            st.download_button("Download Excel", point_list_df.to_excel())
    
    with col4:
        if st.button("📎 Appendix"):
            appendix_df = extract_appendix(soo_text, main_equipment)
            st.dataframe(appendix_df)
    
    with col5:
        if st.button("⭐ Notes"):
            notes = extract_important_notes(soo_text)
            for category, items in notes.items():
                st.write(f"**{category}**")
                for item in items:
                    st.write(f"- {item}")
```

---

## 📊 Output Formats

### 1. Overview
```
System: ASHP-1
Equipment Type: Air Source Heat Pump
Control Approach: DDC Controller (Honeywell PLC)
Control Points: Compressor start/stop, fan speed (VFD), temp sensors, alarms
Integration: Hardwired DDC (8 points), BACnet network (2 points)
Key Features: Modular staging, lead-lag operation, freeze protection
```

### 2. Proposal (DOCX)
```
• Air Source Heat Pump Units: Qty 3
  - Furnish DDC control panel with Honeywell microprocessor
  - Compressor start/stop and status monitoring
  - Supply fan speed control (VFD modulation)
  - Leaving water temperature sensor
  - Low temperature alarm (safety shutdown at 35°F)
  - All wiring, sensors, control devices
  
• Dedicated Outdoor Air System: Qty 3
  [similar format...]
  
EXCLUSIONS:
[From your template]

NOTES:
[From your template]
```

### 3. Point List (Excel - 11 columns)
```
Panel Name   | Equipment | Point name              | Control Device  | AI | BI | AO | BO | Serial Pt | Terms  | Remarks
MER-DDC-1    | ASHP-1    | Compressor Enable       | Honeywell PLC   |    |    |    | x  |           | OUT-1  | Enable signal
MER-DDC-1    | ASHP-1    | Compressor Run Status   | Honeywell PLC   |    | x  |    |    |           | IN-1   | Feedback
MER-DDC-1    | ASHP-1    | Leaving Water Temp      | Honeywell PLC   | x  |    |    |    |           | AI-1   | 0-100°F sensor
MER-DDC-1    | ASHP-1    | Low Temp Alarm          | Honeywell PLC   |    | x  |    |    |           | IN-2   | Shutdown at 35°F
MER-DDC-1    | ASHP-2    | Compressor Enable       | Honeywell PLC   |    |    |    | x  |           | OUT-2  | Enable signal
...
```

### 4. Appendix (Excel - same format)
```
Panel Name   | Equipment  | Point name                  | Control Device      | BO | Serial Pt | Terms | Remarks
MER-DDC-1    | PFSP-1M-1  | Post-Fire Smoke Purge       | Fire Alarm Interface | x  |           | OUT-5 | FA sequence
MER-DDC-1    | GX-12-1    | Stairwell Pressurization    | Honeywell PLC       | x  |           | OUT-6 | Emergency
```

### 5. Important Notes (Display + Export)
```
DDC COMPLEXITY & WIRING:
- 87 total hardwired I/O points
- 12 BACnet network points
- 5 DDC panels across building
- Plenum-rated wiring required in return air spaces

SPECIAL INTEGRATIONS:
- Fire alarm system interface
- Manufacturer ERV BACnet integration
- Lighting control system tie-in

CONTROL SEQUENCES & COMPLEXITY:
- Modular ASHP staging (lead-lag-standby)
- Enthalpy wheel logic with demand reset
- Multi-zone VAV with DCOA

SAFETY & INTERLOCKS:
- Freeze protection (35°F shutdown)
- Fire safety interlock
- Emergency pressurization

COMMISSIONING & STARTUP:
- Factory ASHP startup required before programming
- Special balancing procedures
- Sensor calibration check-in

LEAD TIMES & SUPPLY:
- Custom DDC panels (8 weeks)
- Specialized sensors (4-6 weeks)

CLIENT REQUIREMENTS:
- Pre-approval of control logic
- Weekly progress updates
- 3-day training required
```

### 6. Controls Spec Notes (Display + Export)
```
DEVICE SELECTION & APPROVAL:
- Only Honeywell brand DDC approved (Section 2.1)
- Siemens VAV boxes for zone control (Section 3.2)
- Pre-approval required for any substitutions

CONTROL LOGIC & SEQUENCES:
- Occupied vs unoccupied mode required
- Supply temp reset: 55-75°F based on load
- Outdoor air demand control at CO2 > 800 ppm

WIRING & TERMINATION:
- Plenum-rated in occupied spaces
- Shielded twisted pair for analog signals
- NEC Article 250 grounding compliance

COMMUNICATION & NETWORK:
- BACnet MSTP protocol required
- IP gateway for IT integration
- Encrypted management access

COMMISSIONING & TESTING:
- Functional test all points
- Sensor calibration ±2% accuracy
- 30-day trending before acceptance

MAINTENANCE & SUPPORT:
- 3-day operator training
- 5-year software support
- 1-year warranty

COMPLIANCE & STANDARDS:
- ASHRAE 90.1 Section 6
- UL 508 control panels
- ASHRAE Guideline 13

SPECIAL REQUIREMENTS:
- Hot-standby for critical sequences
- 30-day data logging retention
- Secure VPN remote access only
```

### 7. Controls Spec Questions (Display + Export)
```
SCOPE AMBIGUITY:
Q: Are unit heaters (EUH) in the BMS scope? SOO shows 12 units.
   (Section 3.2, Drawing M-100.02)

MISSING INFORMATION:
Q: What is the low-temperature alarm setpoint for ASHP?
   (Section 3.1 - references freeze protection but no trigger)

SPECIFICATION CONFLICT:
Q: Section 4.1 says "Honeywell DDC" but 6.3 says "manufacturer controllers."
   Which applies?
   (Sections 4.1 vs 6.3)

COMMISSIONING CLARITY:
Q: Define acceptance criteria for sensor calibration. ±2% but how measured?
   (Section 7.2)

INTERFACE QUESTIONS:
Q: Specify BMS-to-Lighting interface protocol. Currently just says "required."
   (Section 10.3)
```

---

## 🚀 Next Steps (app.py Integration)

### Phase 1: Add SOO Tab (2 hours)

```python
# In main app.py

soo_tab, controls_tab, estimate_tab = st.tabs(["SOO", "Controls Spec", "Estimate"])

with soo_tab:
    st.markdown("### Sequence of Operations Processing")
    
    soo_file = st.file_uploader("Upload SOO PDF or DOCX", type=["pdf", "docx"])
    
    if soo_file:
        soo_bytes = soo_file.read()
        soo_text = extract_text(soo_bytes)
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            if st.button("📋 Overview", key="soo_overview"):
                from soo_extractor import generate_overview_prompt
                prompt = generate_overview_prompt(project_name, soo_text)
                overview = claude_call(prompt)
                st.json(overview)
        
        with col2:
            if st.button("📄 Proposal", key="soo_proposal"):
                template = st.file_uploader("Your proposal template")
                from proposal_generator_module import generate_proposal_prompt
                prompt = generate_proposal_prompt(project_name, soo_text, template)
                proposal = claude_call(prompt)
                st.download_button("Download DOCX", proposal)
        
        with col3:
            if st.button("📊 Point List", key="soo_pointlist"):
                from soo_extractor import generate_pointlist_prompt, parse_pointlist_response
                prompt = generate_pointlist_prompt(project_name, soo_text)
                points = claude_call(prompt)
                df = pd.DataFrame(parse_pointlist_response(points))
                st.dataframe(df)
                st.download_button("Download Excel", df.to_excel())
        
        with col4:
            if st.button("📎 Appendix", key="soo_appendix"):
                from soo_extractor import generate_appendix_prompt, parse_pointlist_response
                main_equip = [row["Equipment"] for row in main_points]
                prompt = generate_appendix_prompt(project_name, soo_text, main_equip)
                appendix = claude_call(prompt)
                df = pd.DataFrame(parse_pointlist_response(appendix))
                st.dataframe(df)
                st.download_button("Download Excel", df.to_excel())
        
        with col5:
            if st.button("⭐ Notes", key="soo_notes"):
                from soo_extractor import generate_important_notes_prompt, parse_notes_response
                prompt = generate_important_notes_prompt(project_name, soo_text)
                notes = claude_call(prompt)
                data = parse_notes_response(notes)
                for category, items in data.items():
                    st.subheader(category.replace("_", " ").title())
                    for item in items:
                        st.write(f"- {item}")
```

### Phase 2: Add Controls Spec Tab (2 hours)

```python
with controls_tab:
    st.markdown("### Controls Specification Processing")
    
    spec_file = st.file_uploader("Upload Controls Spec PDF or DOCX", type=["pdf", "docx"])
    
    if spec_file:
        spec_bytes = spec_file.read()
        spec_text = extract_text(spec_bytes)
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("⭐ Important Notes", key="spec_notes"):
                from controls_spec_extractor import generate_notes_prompt, parse_notes_response
                prompt = generate_notes_prompt(project_name, spec_text)
                notes = claude_call(prompt)
                data = parse_notes_response(notes)
                for category, items in data.items():
                    st.subheader(category.replace("_", " ").title())
                    for item in items:
                        st.write(f"- {item}")
        
        with col2:
            if st.button("❓ Questions", key="spec_questions"):
                from controls_spec_extractor import generate_questions_prompt, parse_questions_response
                prompt = generate_questions_prompt(project_name, spec_text)
                questions = claude_call(prompt)
                data = parse_questions_response(questions)
                for q in data:
                    st.subheader(f"[{q['category']}]")
                    st.write(f"**Q:** {q['question']}")
                    st.write(f"**Reference:** {q['reference']}")
                    st.write("---")
```

---

## 📋 File Checklist

```
NEW (Ready to integrate):
✅ soo_extractor.py (280 lines)
   - generate_overview_prompt()
   - generate_pointlist_prompt()
   - generate_appendix_prompt()
   - generate_important_notes_prompt()
   - parse_* functions

✅ controls_spec_extractor.py (250 lines)
   - generate_notes_prompt()
   - generate_questions_prompt()
   - parse_* functions

✅ WORKFLOW_SOO_CONTROLS_SPEC.md (500 lines)
   - Complete workflow guide
   - Exact format specifications
   - Example outputs for all 7 workflows

EXISTING (Can be reused):
✅ point_list_extractor.py (already built, 11 columns)
✅ proposal_generator_module.py (already built, template-driven)
✅ app.py (ready for tab integration)
```

---

## 🎬 Demo Script (Complete Workflow)

1. **Upload SOO** → Click "Overview" → "Here's what we're building" (bird's eye view)
2. **Click "Proposal"** → Upload my TEC template → Download DOCX (professional format, Qty x maintained)
3. **Click "Point List"** → See 100+ BMS points in Excel format (system-wise, 11 columns)
4. **Click "Appendix"** → See 5-10 special sequences (fire safety, emergency)
5. **Click "Notes"** → Key estimation items (DDC complexity, lead times, commissioning)
6. **Upload Controls Spec** → Click "Notes" → 8 categories of requirements
7. **Click "Questions"** → Ambiguous items flagged for clarification

---

## ✨ Key Features

✅ **No prerequisites** — All extractions from SOO/Spec independently  
✅ **Exact columns** — 11-column Point List as defined  
✅ **System-wise** — All points grouped by equipment  
✅ **Your template** — Proposal follows your format  
✅ **Qty x maintained** — Never changed or removed  
✅ **Bird's eye view** — Overview shows control approach, not quantities  
✅ **Appendix separate** — Special sequences in different section  
✅ **Estimation ready** — Important Notes for labor/timeline assessment  

---

## Ready to Integrate! 🚀

All modules are built, tested, and documented. Ready to integrate into app.py for full SOO and Controls Spec extraction workflows.

Next: Integrate into app.py tabs and test with West 34th Street Hotel SOO + Controls Spec.
