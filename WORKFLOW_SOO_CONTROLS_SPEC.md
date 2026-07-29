# Complete Workflow Guide — SOO & Controls Spec Extraction

**Date:** July 29, 2026  
**Format:** Excel Point List with 11 columns (user-defined)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    BMS ESTIMATION TOOL - DOCUMENT PROCESSING            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  SEQUENCE OF OPERATIONS (SOO) Processing                               │
│  ════════════════════════════════════════════════════════════════════  │
│                                                                         │
│  [Upload SOO PDF/DOCX]                                                 │
│           │                                                            │
│           ├─→ Button 1: "Generate Overview"                            │
│           │   Output: System breakdown (control approach, DDC vs mfg)   │
│           │                                                            │
│           ├─→ Button 2: "Generate Proposal"                            │
│           │   (You provide template reference)                         │
│           │   Output: DOCX proposal following your format              │
│           │                                                            │
│           ├─→ Button 3: "Generate Point List"                          │
│           │   Output: Main points in Excel format (11 columns)         │
│           │                                                            │
│           ├─→ Button 4: "Generate Appendix"                            │
│           │   Output: Appendix points (same Excel format)              │
│           │                                                            │
│           └─→ Button 5: "Extract Important Notes"                      │
│               Output: Key estimation points (DDC complexity, etc.)     │
│                                                                         │
│  CONTROLS SPEC Processing                                              │
│  ════════════════════════════════════════════════════════════════════  │
│                                                                         │
│  [Upload Controls Spec PDF/DOCX]                                       │
│           │                                                            │
│           ├─→ Button 1: "Extract Important Notes"                      │
│           │   Output: Requirements, device approvals, compliance       │
│           │                                                            │
│           └─→ Button 2: "Extract Questions"                            │
│               Output: Ambiguous/unclear items flagged for clarification│
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 1. SOO Overview — "Generate Overview"

**Input:** SOO text (8000+ characters)  
**Output:** Bird's eye view of control approach per system  
**Format:** Table/display in Streamlit

### Example Output:

```
System: ASHP-1
Equipment Type: Air Source Heat Pump
Control Approach: DDC Controller (Honeywell PLC)
Control Points: Compressor start/stop, supply fan speed (VFD), leaving water temp sensor, alarm monitoring
Integration: Hardwired DDC (8 points), BACnet network (2 points)
Key Features: Modular staging, lead-lag operation, freeze protection (low temp shutdown at 35°F)

---

System: DOAS-1M-1
Equipment Type: Dedicated Outdoor Air System
Control Approach: DDC Controller (Honeywell PLC) with manufacturer enthalpy interface
Control Points: Supply/exhaust fans, dampers, sensors, enthalpy wheel modulation
Integration: Hardwired DDC (12 points), BACnet to ERV controller (1 interface)
Key Features: Demand-controlled outdoor air, enthalpy wheel optimization
```

**Key Attributes:**
- System tag (ASHP-1, DOAS-1, etc.) — extracted from SOO
- Equipment type — what it is
- Control approach — HIGH-LEVEL (DDC vs manufacturer vs local)
- Control points — what it controls (no quantities)
- Integration — how it connects (hardwired, BACnet, etc.)
- Key features — special sequences, safety, logic

---

## 2. SOO Proposal — "Generate Proposal"

**Input:** 
- Your reference proposal template (DOCX)
- SOO text
- Optional: Project name, client name

**Output:** DOCX proposal following your template format  
**Process:** You provide template → I analyze format → Generate following same structure

### Example Proposal Section (Qty x Format):

```
SCOPE OF WORK:

HVAC SYSTEM CONTROLS

• Air Source Heat Pump Units: Qty 3
  - Furnish DDC control panel with Honeywell microprocessor
  - Provide compressor start/stop and run status monitoring
  - Provide supply fan speed control (VFD modulation 0-10V)
  - Provide leaving water temperature sensor (0-100°F analog input)
  - Provide low temperature alarm (safety shutdown at 35°F)
  - Provide BACnet communication interface
  - Provide all wiring, sensors, terminations, and enclosures
  - Field programming per SOO sequences
  - Commissioning and startup services

• Dedicated Outdoor Air System: Qty 3
  - Furnish DDC control panel with Honeywell microprocessor
  - Provide supply and exhaust fan start/stop and status
  - Provide outdoor air damper modulation control
  - Provide mixed air temperature and humidity sensors
  - Provide supply air pressure monitoring
  - Provide filter differential pressure indication
  - Provide enthalpy wheel speed control
  - Provide BACnet interface to ERV controller
  - All wiring and field programming included

[continues by system...]

EXCLUSIONS:
- Installation labor (provided by mechanical contractor)
- Ductwork or equipment demolition
- Structural modifications
- Fire/smoke damper control (excluded per specification)

NOTES:
- All DDC equipment Honeywell brand as specified
- Prevailing wage labor included
- One-year warranty on parts and labor
```

**Template Analysis:**
- Your template structure is preserved (sections, headings, formatting)
- Qty x notation maintained throughout
- Exclusions and Notes sections copied as-is from template
- New content (Scope, Equipment) generated from SOO

---

## 3. SOO Point List (Main) — "Generate Point List"

**Input:** SOO text  
**Output:** Excel file with YOUR 11-column format (system-wise)  
**Format:**

| Panel Name | Equipment | Point name | Control Device | AI | BI | AO | BO | Serial Pt | Terms | Remarks |
|---|---|---|---|---|---|---|---|---|---|---|
| MER-DDC-1 | ASHP-1 | Compressor Enable | Honeywell PLC | | | | x | | OUT-1 | Enable signal to compressor |
| MER-DDC-1 | ASHP-1 | Compressor Run Status | Honeywell PLC | | x | | | | IN-1 | Proof of operation feedback |
| MER-DDC-1 | ASHP-1 | Leaving Water Temperature | Honeywell PLC | x | | | | | AI-1 | 0-100°F temperature sensor |
| MER-DDC-1 | ASHP-1 | Low Temperature Alarm | Honeywell PLC | | x | | | | IN-2 | Safety shutdown at 35°F |
| MER-DDC-1 | ASHP-2 | Compressor Enable | Honeywell PLC | | | | x | | OUT-2 | Enable signal |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

### Column Definitions:

- **Panel Name:** Where point is wired (e.g., MER-DDC-1, AHU-1-CTL)
- **Equipment:** System/device tag (ASHP-1, DOAS-1M-1, FCU-SC-1, VAV-12, etc.)
- **Point name:** Exact point from SOO (Supply Fan Start/Stop, Leaving Water Temperature, etc.)
- **Control Device:** Controller type (Honeywell PLC, Siemens VAV, Manufacturer controller, etc.)
- **AI, BI, AO, BO, Serial Pt:** Mark "x" if present (not applicable = leave blank)
  - **AI:** Analog Input (temperature, humidity, pressure, flow)
  - **BI:** Binary Input (status, alarms, faults)
  - **AO:** Analog Output (modulation, speed, position)
  - **BO:** Binary Output (start/stop, enable/disable)
  - **Serial Pt:** Network/BACnet point
- **Terms:** Terminal designation (OUT-1, IN-2, AI-1, etc.) or connection info
- **Remarks:** Point-specific notes from SOO

### Organization:
**System-wise** — All ASHP-1 points together, then ASHP-2, then DOAS-1M-1, then FCU-SC-1, etc.

---

## 4. SOO Point List Appendix — "Generate Appendix"

**Input:** SOO text + main equipment list  
**Output:** Excel file (same 11-column format)  
**Includes:** Special sequences NOT in main list

### Appendix Includes:

- Post-fire smoke purge sequences (PFSP, GX, SPF, HPF)
- Life safety / emergency pressurization
- Stairwell/hoistway control
- Fire alarm integration
- Emergency generator monitoring
- Backup power / UPS monitoring
- Future expansion points
- High-priority override sequences

### Example Appendix Rows:

| Panel Name | Equipment | Point name | Control Device | AI | BI | AO | BO | Serial Pt | Terms | Remarks |
|---|---|---|---|---|---|---|---|---|---|---|
| MER-DDC-1 | PFSP-1M-1 | Post-Fire Smoke Purge Enable | Fire Alarm Interface | | | | x | | OUT-5 | Activated by FA, priority override |
| MER-DDC-1 | GX-12-1 | Stairwell Pressurization | Honeywell PLC | | | | x | | OUT-6 | Emergency-only, manual verification |
| MER-DDC-1 | SPF-35-1 | Smoke Exhaust Fan | Honeywell PLC | | | | x | | OUT-7 | Interlock with stairwell pressurization |

### Organization:
**Same system-wise format** as main list

---

## 5. SOO Important Notes — "Extract Important Notes"

**Input:** SOO text  
**Output:** Categorized notes for estimation (7 categories)  
**Use Case:** Help with labor estimates, timelines, complexity assessment

### Categories & Examples:

#### DDC Complexity & Wiring
```
- 87 total hardwired I/O points (vs typical 40-50)
- 12 BACnet network points
- Multiple DDC controllers needed (5 panels across building)
- Plenum-rated wiring required in all return air spaces
- Special grounding/shielding for long sensor runs
```

#### Special Integrations
```
- Fire alarm system integration (4-wire interface required)
- Manufacturer ERV controller BACnet integration
- Third-party lighting control system interface
- Custom CO2 sensor network (separate from DDC)
- Building energy management system tie-in
```

#### Control Sequences & Complexity
```
- Modular staging (3 ASHP in lead-lag-standby configuration)
- Enthalpy wheel logic with outdoor air demand reset
- Multi-zone VAV with demand-controlled outside air
- Dynamic reset of supply water temperature
- Complex interlock logic for emergency sequences
```

#### Safety & Interlocks
```
- Freeze protection (low limit alarm at 35°F with compressor shutdown)
- Fire safety interlock (automatic smoke exhaust on alarm)
- Emergency pressurization on stairwells
- Low-pressure alarms with pump protection
- Interlock between multiple systems
```

#### Commissioning & Startup
```
- Requires factory startup of ASHP units before BMS programming
- Special balancing procedures for VAV boxes
- Sensor calibration check-in required before final acceptance
- Performance testing with building fully occupied
- Documentation of all setpoints and alarm thresholds
```

#### Lead Times & Supply
```
- Custom DDC panels (8 weeks lead time)
- Specialized pressure sensors (4 weeks)
- Custom CO2 sensor heads (6 weeks)
- BMS network cabling (material only, labor independent)
```

#### Client Requirements
```
- Pre-approval of all control logic sequences
- Weekly progress updates required
- BMS training for facilities team (3 days)
- Spare parts package (1 year supply of common items)
```

---

## 6. Controls Spec Important Notes — "Extract Important Notes"

**Input:** Controls Spec text (PDF/DOCX)  
**Output:** Categorized requirements for project execution  
**Format:** 8 categories

### Categories & Examples:

#### Device Selection & Approval
```
- Only Honeywell brand controllers approved (Section 2.1)
- Siemens VAV boxes for all zone control (Section 3.2)
- Belimo actuators for all proportional control (Section 3.3)
- Pre-approval required for any substitutions
- Five approved manufacturers for CO2 sensors (Appendix A)
```

#### Control Logic & Sequences
```
- Occupied vs unoccupied mode operation required (Section 4.1)
- Supply water temperature reset: 55°F to 75°F based on load (Section 4.2)
- Outdoor air demand control enabled when CO2 > 800 ppm (Section 4.3)
- Emergency shutdown on low supply pressure (5 psig) (Section 4.4)
```

#### Wiring & Termination
```
- All wiring in occupied spaces must be plenum-rated (Section 5.1)
- Cable labeling per ANSI standard (Section 5.2)
- Shielded twisted pair for all analog sensor wiring (Section 5.3)
- Equipment grounding per NEC Article 250 (Section 5.4)
```

#### Communication & Network
```
- BACnet MSTP protocol for all DDC communication (Section 6.1)
- Network termination resistors at each end (Section 6.2)
- BACnet/IP gateway required for IT integration (Section 6.3)
- Cybersecurity: Encrypted management access (Section 6.4)
```

#### Commissioning & Testing
```
- Functional performance test on all points (Section 7.1)
- Sensor calibration verification (±2% accuracy) (Section 7.2)
- Sequence of operation walk-through with owner (Section 7.3)
- 30-day trending period before final acceptance (Section 7.4)
```

#### Maintenance & Support
```
- Three-day operator training required (Section 8.1)
- BMS software support for 5 years (Section 8.2)
- One-year parts and labor warranty (Section 8.3)
- Annual preventive maintenance contract (optional) (Section 8.4)
```

#### Compliance & Standards
```
- Energy code: ASHRAE 90.1 Section 6 (Section 9.1)
- Safety: UL 508 control panels (Section 9.2)
- Building automation: ASHRAE Guideline 13 (Section 9.3)
- Cybersecurity: NERC CIP standards if applicable (Section 9.4)
```

#### Special Requirements
```
- System redundancy: Hot-standby for critical sequences (Section 10.1)
- Data logging: 30-day minimum retention (Section 10.2)
- Remote access: Secure VPN only (Section 10.3)
- Custom graphics for owner's web portal (Section 10.4)
```

---

## 7. Controls Spec Questions — "Extract Questions"

**Input:** Controls Spec text  
**Output:** List of ambiguous/missing items flagged for clarification  
**Format:** JSON with category + question + reference

### Example Questions:

```
Category: SCOPE AMBIGUITY
Question: Are the 12 unit heaters (EUH) shown on drawing M-100.02 included 
          in the BMS control scope?
Reference: Section 3.2, Drawing M-100.02
```

```
Category: MISSING INFORMATION
Question: What is the required low-temperature alarm setpoint for ASHP?
          Section 3.1 references "freeze protection" but doesn't specify trigger.
Reference: Section 3.1 - ASHP Sequence
```

```
Category: SPECIFICATION CONFLICT
Question: Section 4.1 specifies Honeywell DDC, but Section 6.3 requires 
          "manufacturer-provided controllers for all packaged units." Clarify scope.
Reference: Sections 4.1 vs 6.3
```

```
Category: COMMISSIONING CLARITY
Question: What are the acceptance criteria for sensor calibration?
          Section 7.2 requires "±2% accuracy" but measurement method undefined.
Reference: Section 7.2
```

```
Category: INTERFACE QUESTIONS
Question: Specify the interface protocol between BMS and building lighting control.
          Current spec only says "integration required."
Reference: Section 10.3
```

---

## Workflow Summary

### From SOO (Sequence of Operations):

| Button | Output | Purpose | Format |
|--------|--------|---------|--------|
| Overview | System breakdown, control approach | Understand scope at a glance | Display table |
| Proposal | Complete DOCX proposal | Generate proposal following your template | DOCX download |
| Point List | Main points (11 columns) | Detailed I/O specification | Excel file |
| Appendix | Appendix points (11 columns) | Special sequences | Excel file |
| Important Notes | Estimation key points | Labor/timeline estimation | Display + export |

### From Controls Spec (Controls Specification):

| Button | Output | Purpose | Format |
|--------|--------|---------|--------|
| Important Notes | 8-category requirements | Understand spec details | Display + export |
| Questions | Flagged ambiguities | Identify clarifications needed | Display + export |

---

## Implementation Notes

- **All outputs are independent** — No prerequisite between SOO and Controls Spec workflows
- **Proposal requires your template** — You provide format, I generate following it (Qty x maintained)
- **Point List format is fixed** — 11 columns as defined above
- **System-wise organization** — All points grouped by Equipment tag
- **I/O type inference** — Auto-marked with "x" from SOO analysis
- **Appendix separate** — Special sequences in different section

---

## Next Steps

1. Finalize Point List format (11 columns confirmed)
2. Integrate SOO extraction module into app.py
3. Integrate Controls Spec extraction module into app.py
4. Test with West 34th Street Hotel SOO + Spec
5. Demo to stakeholders
