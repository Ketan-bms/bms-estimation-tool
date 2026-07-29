"""
soo_extractor.py
COMPLETE SOO extraction module - FULL VERSION with real prompts
"""

import json
import re


def generate_overview_prompt(project_name, soo_text):
    """Generate prompt for SOO Overview - bird's eye view."""
    prompt = f"""You are a senior BMS engineer. Extract a HIGH-LEVEL overview of the SOO.

PROJECT: {project_name}

SEQUENCE OF OPERATIONS:
{soo_text[:8000]}

Return ONLY JSON:
{{
  "overview": [
    {{
      "System": "ASHP-1",
      "Equipment_Type": "Air Source Heat Pump", 
      "Control_Approach": "DDC with Honeywell PLC",
      "Control_Points": "Compressor on/off, supply fan speed modulation, water temp sensor",
      "Integration": "Hardwired 8 I/O points, BACnet network",
      "Key_Features": "Modular staging, freeze protection, lead-lag operation"
    }}
  ]
}}

RULES:
- System: Equipment tag (ASHP-1, DOAS-1, FCU-1)
- Equipment_Type: What it is
- Control_Approach: DDC vs Manufacturer controller (HIGH LEVEL)
- Control_Points: What this system controls (no quantities)
- Integration: How it connects (hardwired, BACnet, etc)
- Key_Features: Special sequences, safety, interlocks

NO markdown. START with {{ END with }}"""
    return prompt


def generate_pointlist_prompt(project_name, soo_text):
    """Generate prompt for Point List extraction."""
    prompt = f"""You are a BMS engineer. Extract ALL BMS points from this SOO.

PROJECT: {project_name}

SEQUENCE OF OPERATIONS:
{soo_text[:8000]}

Return ONLY JSON array:
[
  {{
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
    "Remarks": "Enable signal to compressor"
  }}
]

RULES:
- ONE ROW PER POINT (not per device)
- Extract EVERY point mentioned in SOO
- System-wise order (ASHP-1 all points, then ASHP-2, then DOAS, etc)
- Panel Name: Infer from system tag
- Equipment: System/device tag
- Point name: Exact name from SOO
- Control Device: Honeywell, Siemens, Manufacturer, etc
- I/O columns: Mark with "x" if present
  - AI = Analog Input (sensors: temp, humidity, pressure, flow)
  - BI = Binary Input (status, alarms, fault signals)
  - AO = Analog Output (modulation, speed, position)
  - BO = Binary Output (start/stop, enable/disable commands)
  - Serial Pt = BACnet/Modbus network points
- Terms: Terminal/connection info
- Remarks: Notes from SOO

NO markdown. START with [ END with ]"""
    return prompt


def generate_appendix_prompt(project_name, soo_text, main_equipment):
    """Generate prompt for Appendix points."""
    main_str = ", ".join(main_equipment) if main_equipment else ""
    prompt = f"""You are a BMS engineer. Extract SPECIAL/APPENDIX points from SOO.

PROJECT: {project_name}

Main equipment already in list: {main_str}

SEQUENCE OF OPERATIONS:
{soo_text[:8000]}

Return ONLY JSON array:
[
  {{
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
    "Remarks": "Activated by fire alarm system"
  }}
]

APPENDIX POINTS ONLY - DO NOT repeat main list:
- Post-fire smoke purge sequences (PFSP, GX, HPF, SPF)
- Life safety / emergency pressurization systems
- Stairwell / hoistway pressurization
- Fire alarm integration points
- Emergency shutdown sequences
- Future expansion points
- Backup/UPS monitoring

Same columns as main list.
NO markdown. START with [ END with ]"""
    return prompt


def generate_important_notes_prompt(project_name, soo_text):
    """Generate prompt for Important Notes - estimation."""
    prompt = f"""You are a BMS project estimator. Extract key points for project estimation.

PROJECT: {project_name}

SEQUENCE OF OPERATIONS:
{soo_text[:8000]}

Return ONLY JSON:
{{
  "ddc_complexity": [
    "87 total hardwired I/O points distributed across 3 panels",
    "12 BACnet network points",
    "Plenum-rated wiring required in return air spaces",
    "Long sensor runs require shielded twisted pair"
  ],
  "special_integrations": [
    "Fire alarm system 4-wire interface required",
    "Manufacturer ERV controller BACnet integration",
    "Third-party lighting control system tie-in"
  ],
  "control_sequences": [
    "Modular ASHP staging (lead-lag-standby configuration)",
    "Enthalpy wheel logic with demand reset",
    "Multi-zone VAV with demand-controlled outside air",
    "Dynamic reset of supply water temperature"
  ],
  "safety_interlocks": [
    "Freeze protection with low temp alarm at 35°F and compressor shutdown",
    "Fire safety interlock with automatic smoke exhaust on alarm",
    "Low-pressure alarm with pump protection interlock",
    "Emergency pressurization on stairwells"
  ],
  "commissioning": [
    "Factory startup of ASHP units required before programming",
    "Special balancing procedures for VAV boxes",
    "Sensor calibration check-in before final acceptance",
    "Performance testing with building fully occupied"
  ],
  "lead_times": [
    "Custom DDC panels - 8 weeks lead time",
    "Specialized pressure sensors - 4-6 weeks",
    "BMS network cabling - material only, labor separate"
  ],
  "client_requirements": [
    "Pre-approval of all control logic sequences",
    "BMS training for facilities team (3 days)",
    "Spare parts package (1 year supply)",
    "One-year parts and labor warranty"
  ]
}}

Extract ALL key points for estimation:
- DDC complexity (I/O count, wiring, panels, special requirements)
- Special integrations (fire alarm, manufacturer, third-party)
- Control sequences (staging, reset logic, multi-zone)
- Safety & interlocks (freeze protection, emergency, alarms)
- Commissioning (startup, balancing, testing, training)
- Lead times (custom hardware, sensors, special materials)
- Client requirements (approvals, training, warranty)

NO markdown. START with {{ END with }}"""
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
