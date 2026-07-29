# Three Independent Workflows — Decoupled Architecture

**Date:** July 29, 2026  
**Purpose:** SOO Overview, Proposal Generator, Point List (independent, no prerequisites)

---

## Workflow Architecture

```
                        STREAMLIT APP
                       /     |     \
                      /      |      \
         ┌────────────┴──┐   │   ┌──┴────────────┐
         │                │   │   │                │
    [Tab 1: SOO Overview]  │  [Tab 3: Point List]
         │                │   │   │                │
         └────────────┬──┘   │   └──┬────────────┘
                      │      │      │
    ┌─────────────────┴──────┴──────┴──────────────┐
    │         [Tab 2: Create Proposal]             │
    └──────────────────────────────────────────────┘
                      │
         (All independent — no linking)
```

---

## Tab 1: SOO Overview

**Purpose:** Understand the scope at a glance — no Point List or Proposal needed.

### Three Sub-tabs:

#### 1A. Summary Table
```
System    Qty    Description                    SOO Section
ASHP      3      Air Source Heat Pump           Section 3.1
DOAS      3      Dedicated Outdoor Air System   Section 3.2
AHU       2      Air Handling Units             Section 3.3
FCU       8      Fan Coil Units (2-pipe)        Section 3.4
VAV       60     Variable Air Volume boxes      Section 3.5
ERV       2      Energy Recovery Units          Section 3.6
CHWP      3      Chilled Water Pumps            Section 4.1
PHWP      3      Primary Hot Water Pumps        Section 4.2
EF        5      Exhaust Fans                   Section 5.1
```

#### 1B. System-wise Breakdown
```
Equipment    Type                     Qty    Points    Controls
ASHP-1       Air Source Heat Pump     1      8         Compressor start/stop, status, temp sensors, alarms
ASHP-2       Air Source Heat Pump     1      8         (same)
ASHP-3       Air Source Heat Pump     1      8         (same)
DOAS-1M-1    Dedicated OA System      1      15        Supply/exhaust fans, dampers, sensors, enthalpy wheel
...
```

#### 1C. Labor Hours Estimate
```
System    Equipment Count    Points/Equipment    Total Points    Eng    Prog    Int    Graphics    Startup
ASHP      3                 8                   24              12     24      12     12          12
DOAS      3                 15                  45              22.5   45      22.5   22.5        22.5
AHU       2                 12                  24              12     24      12     12          12
...
```

### User Action:
1. Upload SOO PDF (Takeoff tab or directly)
2. Click "Generate Overview"
3. View 3 tabs with system breakdown
4. Export to Excel (3 sheets: Summary, Breakdown, Labor)

**No Point List or Proposal required.**

---

## Tab 2: Create Proposal

**Purpose:** Generate professional proposals following user's preferred format.

### Workflow:

1. **Upload Proposal Template** (optional)
   - User provides a reference DOCX proposal
   - AI analyzes format, sections, tone
   - Future proposals follow same structure

2. **Provide SOO Reference**
   - Text area: User pastes or uploads SOO snippets relevant to proposal
   - Or: Select pre-uploaded SOO file
   - AI extracts scope from SOO text

3. **Generate Proposal**
   - Click "Generate Proposal from Template"
   - AI creates DOCX proposal with:
     - All sections matching user's template structure
     - Equipment organized by system (ASHP → DOAS → FCU, etc.)
     - **Qty x notation** (e.g., "Qty 3" for ASHP systems)
     - Specific control points listed per system
     - Standard TEC language (if no template provided)
     - Pricing placeholders ($ XX)
     - Exclusions list
     - Notes & clarifications

4. **Export/Download**
   - Download as DOCX
   - Edit in Word if needed
   - Re-upload for refinement

### Template Format Guidance (if none provided):

Default TEC proposal structure:
- **Header:** Date, Bid No, Project Name
- **Documents Referenced:** Drawings, Specs, Prep by
- **Scope of Work:** By system, with Qty x notation
- **Pricing:** Base scope + Alternates
- **Notes & Clarifications:** Standard TEC disclaimers
- **Exclusions:** Clear what's NOT included
- **Signature:** TEC Building Systems, LLC

### Example Scope Section (maintaining Qty x):
```
HVAC SYSTEM CONTROLS:

• Air Source Heat Pump Units: Qty 3
  - Furnish DDC control panel with microprocessor
  - Provide compressor start/stop and status monitoring
  - Provide supply fan speed control (VFD modulation)
  - Provide leaving water temperature sensor
  - Provide low temperature alarm (safety shutdown)
  - Provide BACnet interface to main DDC

• Dedicated Outdoor Air System: Qty 3
  - Furnish DDC control panel with microprocessor
  - Supply/exhaust fan start/stop and status
  - Outdoor air damper modulation
  - Mixed air temperature and humidity sensors
  - Supply air pressure and filter differential monitoring
  - Enthalpy wheel speed control
  - Provide all wiring, sensors, and control devices

[continues by system...]
```

**No Point List or Overview required.**

---

## Tab 3: Point List

**Purpose:** Detailed I/O point extraction and organization by system.

### Two Sections:

#### 3A. Main Point List
BMS-specific columns (11 total):
- Panel Name
- Equipment
- Point Name
- Control Device
- AI, BI, AO, BO, Serial_Pt (marked with 'x')
- Terms
- Remarks

**Organization:** System-wise (all ASHP-1 points together, then ASHP-2, etc.)

Example:
```
Panel Name    Equipment    Point Name                    AI  BI  AO  BO  Serial_Pt  Terms      Remarks
MER-DDC-1     ASHP-1       Compressor Enable                         x               OUT-1      Enable signal
MER-DDC-1     ASHP-1       Compressor Run Status             x                       IN-1       Proof of operation
MER-DDC-1     ASHP-1       Leaving Water Temperature     x                           AI-1       0-100°F sensor
MER-DDC-1     ASHP-1       Low Temp Alarm                    x                       IN-2       Shutdown at 35°F
MER-DDC-1     ASHP-2       (same pattern for ASHP-2)
...
```

**User Actions:**
- Generate from SOO
- Edit any cell in data editor
- Delete/add rows
- Export to Excel

#### 3B. Appendix Section
**For additional/special points:**
- Post-fire smoke purge sequences (PFSP, GX, etc.)
- Life safety / emergency pressurization
- Future expansion points
- Special integrations (Fire alarm, Backup power)
- Historical/archived sequences

**Same 11-column structure, organized system-wise:**

```
Panel Name    Equipment    Point Name                    AI  BI  AO  BO  Serial_Pt  Terms      Remarks
MER-DDC-1     PFSP-1M-1    Post-Fire Smoke Purge                    x               OUT-5      Activated by FA
MER-DDC-1     GX-12-1      Stair Pressurization Fan                 x               OUT-6      Emergency only
MER-DDC-1     SPF-35-1     Hoistway Exhaust Fan                     x               OUT-7      Interlock with elev
...
```

**User Actions:**
- Generate appendix points from SOO
- Manually add additional points
- Combine main + appendix in one export
- Or export separately

### Workflow:
1. Upload SOO (or reference existing)
2. Click "Generate Main Point List"
3. Optionally: Click "Generate Appendix Points"
4. Edit both sections in data editors
5. Export to Excel (2 sheets: Main, Appendix — or combined)

**No Overview or Proposal required.**

---

## Independence Matrix

| Workflow | Requires Takeoff | Requires Proposal | Requires Overview | Prerequisite |
|----------|------------------|-------------------|-------------------|--------------|
| SOO Overview | No | No | No | SOO only |
| Create Proposal | No | No | No | SOO + template (optional) |
| Point List | No | No | No | SOO only |

**All three are independent.** User can do any in any order.

---

## Data Flow

### SOO Overview
```
Upload SOO PDF/DOCX
         ↓
   Extract text
         ↓
Generate overview prompt → Send to Claude
         ↓
Parse JSON response
         ↓
Create 3 dataframes (Summary, Breakdown, Labor)
         ↓
Display in tabs / Export to Excel
```

### Create Proposal
```
Upload template DOCX (optional)
         ↓
Analyze template structure
         ↓
User provides SOO text/snippets
         ↓
Generate proposal prompt → Send to Claude
         ↓
Generate DOCX following template format
         ↓
Download / Edit
```

### Point List
```
Upload SOO PDF/DOCX
         ↓
Extract text
         ↓
Generate main points prompt → Send to Claude
         ↓
Parse JSON + infer I/O types
         ↓
Display in data editor
         ↓
[Optionally] Generate appendix points
         ↓
Export main + appendix to Excel
```

---

## Column Definitions (Point List)

| Column | Source | Inference | Example |
|--------|--------|-----------|---------|
| Panel Name | SOO or inferred | Yes | MER-DDC-1 |
| Equipment | SOO (tag) | No | ASHP-1, DOAS-1M-1 |
| Point Name | SOO (point description) | No | Compressor Enable |
| Control Device | SOO | Yes | Honeywell PLC |
| AI | Inferred from point name | Yes | x (temperature sensor) |
| BI | Inferred from point name | Yes | x (status/alarm) |
| AO | Inferred from point name | Yes | x (modulation) |
| BO | Inferred from point name | Yes | x (start/stop) |
| Serial_Pt | Inferred from point name | Yes | x (BACnet) |
| Terms | SOO | No | OUT-1, AI-1 |
| Remarks | SOO | No | Energize to enable |

---

## Example Outputs

### SOO Overview → Export Excel
**Sheet 1: Summary**
```
System  Qty  Description                SOO_Section
ASHP    3    Air Source Heat Pump       3.1
DOAS    3    Dedicated Outdoor Air      3.2
```

**Sheet 2: System Breakdown**
```
Equipment  Type                  Qty  Points  Compressor_Control  Temp_Sensors
ASHP-1     Heat Pump             1    8       BO                  AI
DOAS-1M-1  Outdoor Air System    1    15      AO                  AI
```

**Sheet 3: Labor Hours**
```
System  Equipment_Count  Total_Points  Engineering  Programming  Integration
ASHP    3                24            12           24            12
DOAS    3                45            22.5         45            22.5
```

### Create Proposal → Download DOCX
Formatted DOCX with:
- Professional header
- Scope by system (with Qty x)
- Equipment list
- Pricing placeholders
- TEC standard language

### Point List → Export Excel
**Sheet 1: Main**
```
Panel_Name  Equipment  Point_Name              AI  BO  BI  AO  Serial_Pt  Terms  Remarks
MER-DDC-1   ASHP-1     Compressor Enable           x                      OUT-1  Enable
MER-DDC-1   ASHP-1     Leaving Water Temp      x                          AI-1   Sensor
```

**Sheet 2: Appendix**
```
Panel_Name  Equipment  Point_Name                  BO  Terms  Remarks
MER-DDC-1   PFSP-1M-1  Post-Fire Smoke Purge       x   OUT-5  FA sequence
```

---

## UI Structure (app.py)

```python
def main():
    # Top-level navigation
    tab1, tab2, tab3 = st.tabs(["📋 SOO Overview", "📄 Create Proposal", "📊 Point List"])
    
    with tab1:
        module_soo_overview(p)  # New module
    
    with tab2:
        module_proposal(p)      # New module
    
    with tab3:
        module_point_list(p)    # Enhanced module (with appendix)
```

Each module is completely independent:
- Separate state
- Separate uploads (SOO can be uploaded 3 times, once per tab)
- No cross-dependencies
- Can use different SOO files in each tab if needed

---

## Next Steps (Implementation)

1. Create `soo_overview_module.py` ✅
2. Create `proposal_generator_module.py` ✅
3. Update `point_list_extractor.py` with appendix ✅
4. Update `app.py` to add 3 independent tabs
5. Test each workflow independently
6. Deploy to Streamlit Cloud

---

## Key Principles

✅ **No prerequisites** — Any workflow can run standalone  
✅ **SOO is optional for each tab** — Or provide snippets/text  
✅ **Template-driven proposals** — User defines format  
✅ **System-wise organization** — All tabs group by equipment  
✅ **Qty x notation** — Maintained throughout (never removed)  
✅ **Appendix support** — Main + supplementary points  
✅ **Export flexibility** — Excel with multiple sheets  

---

## Demo Narrative (Using All Three)

1. **SOO Overview:** Upload SOO → Show 3-tab breakdown → "Here's the full system scope"
2. **Create Proposal:** Reference TEC template → Generate proposal → "Professional format, ready to customize"
3. **Point List:** Generate main points → Show appendix points → "100+ BMS points organized by system"

All done independently — no data dependencies.
