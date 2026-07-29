"""
soo_extractor.py
Extract from SOO (Sequence of Operations):
1. Overview (system breakdown, control approach, no quantities)
2. Proposal (user provides template, follow format)
3. Point List (main + appendix in user's Excel format)
4. Important Notes (for estimation)
"""

import json
import re


def generate_overview_prompt(project_name, soo_text):
    """Generate prompt for SOO Overview - bird's eye view of sequence."""
    
    prompt = f"""You are a senior BMS controls engineer. Extract a bird's eye overview of the SOO.

PROJECT: {project_name}

SEQUENCE OF OPERATIONS:
{soo_text}

OUTPUT: Return JSON with this structure:

{{
  "overview": [
    {{
      "System": "ASHP-1",
      "Equipment_Type": "Air Source Heat Pump",
      "Control_Approach": "DDC Controller (Honeywell PLC) with compressor staging and freeze protection",
      "Control_Points": "Compressor start/stop, fan speed modulation (VFD), valve modulation, temperature sensors, alarms",
      "Integration": "Hardwired DDC points (8), BACnet network (2)",
      "Key_Features": "Modular staging, lead-lag operation, low temperature shutdown"
    }},
    ...
  ]
}}

RULES:
- System: Equipment tag (e.g., ASHP-1, DOAS-1M-1, FCU-SC-5)
- Equipment_Type: What it is (Heat Pump, DOAS, AHU, FCU, VAV, etc.)
- Control_Approach: HIGH-LEVEL approach (e.g., "DDC Controller" vs "Manufacturer provided controller" vs "Local thermostat")
- Control_Points: What this system controls (fan start/stop, valve modulation, sensors, alarms, etc.) - NOT quantities
- Integration: How it connects (hardwired DDC, BACnet, Modbus, local control, etc.)
- Key_Features: Special sequences, interlocks, safety features

DO NOT include quantities of equipment. Focus on control strategy and approach.

CRITICAL: Start with {{ and end with }}. No markdown."""
    
    return prompt


def generate_pointlist_prompt(project_name, soo_text, takeoff_equip=None):
    """Generate prompt for Point List extraction in user's format."""
    
    example_row = {
        "Panel Name": "MER-DDC-1",
        "Equipment": "ASHP-1",
        "Point name": "Compressor Enable",
        "Control Device": "Honeywell PLC",
        "AI": "",
        "BI": "",
        "AO": "",
        "BO": "x",
        "Serial Pt": "",
        "Terms": "OUT-1",
        "Remarks": "Enable signal to compressor contactor"
    }
    
    prompt = f"""You are a senior BMS controls engineer. Extract MAIN point list from SOO.

PROJECT: {project_name}

SEQUENCE OF OPERATIONS:
{soo_text}

OUTPUT: Return JSON array of BMS points with EXACTLY these columns:
Panel Name, Equipment, Point name, Control Device, AI, BI, AO, BO, Serial Pt, Terms, Remarks

Use "x" to mark present I/O types (AI, BI, AO, BO, Serial Pt). Leave blank if not applicable.

RULES:
- ONE ROW PER POINT (not per device)
- Extract EVERY point mentioned in SOO
- System-wise organization (all ASHP-1 points together, then ASHP-2, etc.)
- Panel Name: Infer from system prefix (e.g., MER-DDC-1 for MER equipment)
- Equipment: Equipment tag from SOO (ASHP-1, DOAS-1M-1, FCU-SC-5, etc.)
- Point name: Exact point from SOO (Supply Fan Start/Stop, Leaving Water Temperature, etc.)
- Control Device: Honeywell PLC, BACnet Gateway, Manufacturer controller, etc.
- AI/BI/AO/BO/Serial Pt: Mark with "x" if present
  - AI: Analog Input (temperature, humidity, pressure, flow sensors)
  - BI: Binary Input (status, alarms, fault signals)
  - AO: Analog Output (modulation, position control, setpoint)
  - BO: Binary Output (start/stop, enable/disable commands)
  - Serial Pt: BACnet/Modbus/network points
- Terms: Terminal designation (e.g., OUT-1, IN-2, AI-1)
- Remarks: Operational notes from SOO

CRITICAL: Start with [ and end with ]. No markdown.

Example row:
{json.dumps([example_row])}

Extract ALL main points:"""
    
    return prompt


def generate_appendix_prompt(project_name, soo_text, main_equipment):
    """Generate prompt for Point List Appendix - special sequences."""
    
    example_row = {
        "Panel Name": "MER-DDC-1",
        "Equipment": "PFSP-1M-1",
        "Point name": "Post-Fire Smoke Purge Enable",
        "Control Device": "Fire Alarm Interface",
        "AI": "",
        "BI": "",
        "AO": "",
        "BO": "x",
        "Serial Pt": "",
        "Terms": "OUT-5",
        "Remarks": "Activated by fire alarm system; special sequence"
    }
    
    main_equip_str = ", ".join(main_equipment) if main_equipment else "None"
    
    prompt = f"""You are a senior BMS controls engineer. Extract APPENDIX points from SOO.

PROJECT: {project_name}

Equipment already in main point list: {main_equip_str}

SEQUENCE OF OPERATIONS:
{soo_text}

OUTPUT: Return JSON array of special/appendix points with EXACTLY these columns:
Panel Name, Equipment, Point name, Control Device, AI, BI, AO, BO, Serial Pt, Terms, Remarks

APPENDIX INCLUDES ONLY:
- Post-fire smoke purge sequences (PFSP, GX, SPF, HPF)
- Life safety / emergency pressurization
- Stairwell/hoistway pressurization
- Fire alarm integration points
- Emergency generator monitoring
- Backup power / UPS monitoring
- Future expansion points
- Special high-priority sequences

DO NOT repeat equipment already in main list.

Use "x" for present I/O types. Leave blank if not applicable.

RULES:
- ONE ROW PER POINT
- System-wise organization
- Same column format as main point list
- Mark each with appropriate I/O types
- Include remarks explaining why it's appendix

CRITICAL: Start with [ and end with ]. No markdown.

Example:
{json.dumps([example_row])}

Extract APPENDIX points only (not in main list):"""
    
    return prompt


def generate_important_notes_prompt(project_name, soo_text):
    """Generate prompt for Important Notes - for estimation."""
    
    prompt = f"""You are a senior BMS project estimator. Extract important notes from SOO for project estimation.

PROJECT: {project_name}

SEQUENCE OF OPERATIONS:
{soo_text}

EXTRACT THESE CATEGORIES (as separate lists):

1. DDC COMPLEXITY & WIRING:
   - Number of hardwired I/O points
   - Number of network/BACnet points
   - Special wiring requirements (plenum-rated, conduit, etc.)
   - Panel complexity (standalone vs large central)
   - Communication protocols needed

2. SPECIAL INTEGRATIONS:
   - Fire alarm interface required
   - BMS to manufacturer controller integration
   - Third-party system connections (lighting, security, etc.)
   - Special sensor types (CO2, humidity, enthalpy, etc.)

3. CONTROL SEQUENCES & COMPLEXITY:
   - Modular staging logic (lead-lag)
   - Enthalpy wheel modulation
   - Multi-zone control
   - VFD speed control complexity
   - Reset logic or adaptive setpoints

4. SAFETY & INTERLOCKS:
   - Freeze protection sequences
   - Emergency pressurization
   - Fire/smoke damper coordination
   - Low limit alarms
   - Interlock requirements

5. COMMISSIONING & STARTUP:
   - Special startup sequences
   - Calibration requirements
   - Balancing requirements
   - Training needs
   - Performance testing

6. LEAD TIMES & SUPPLY:
   - Custom control panels
   - Special sensors
   - Manufacturer-specific hardware
   - Network infrastructure

7. CLIENT REQUIREMENTS:
   - Pre-approval items
   - Special documentation
   - Specific commissioning procedures
   - Warranty terms

OUTPUT: Return JSON:

{{
  "ddc_complexity": ["point 1", "point 2", ...],
  "special_integrations": ["point 1", ...],
  "control_sequences": ["point 1", ...],
  "safety_interlocks": ["point 1", ...],
  "commissioning": ["point 1", ...],
  "lead_times": ["point 1", ...],
  "client_requirements": ["point 1", ...]
}}

CRITICAL: Start with {{ and end with }}. No markdown.
Focus on details that affect estimation (labor hours, complexity, timeline)."""
    
    return prompt


def parse_pointlist_response(raw_response):
    """Parse point list JSON array from Claude response."""
    if not raw_response:
        return []
    try:
        text = str(raw_response).strip()
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1:
            return []
        json_str = text[start:end+1]
        result = json.loads(json_str)
        return result if isinstance(result, list) else []
    except Exception as e:
        return []


def parse_notes_response(raw_response):
    """Parse notes JSON object from Claude response."""
    if not raw_response:
        return {}
    try:
        text = str(raw_response).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return {}
        json_str = text[start:end+1]
        result = json.loads(json_str)
        return result if isinstance(result, dict) else {}
    except Exception as e:
        return {}


if __name__ == "__main__":
    print("SOO Extractor Module Ready")
    print("=" * 70)
    print("\nFunctions:")
    print("  1. generate_overview_prompt() - Bird's eye view")
    print("  2. generate_pointlist_prompt() - Main points extraction")
    print("  3. generate_appendix_prompt() - Appendix points extraction")
    print("  4. generate_important_notes_prompt() - Estimation notes")
