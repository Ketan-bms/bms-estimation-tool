"""
soo_extractor.py - FIXED VERSION
Crystal-clear prompts that get the RIGHT data structure
"""

import json
import re


def generate_overview_prompt(project_name, soo_text):
    """Generate prompt for SOO Overview - EXTRACT SYSTEMS ONLY."""
    
    prompt = f"""EXTRACT ONLY HVAC SYSTEMS AND EQUIPMENT FROM THIS SOO.

PROJECT: {project_name}

SOO TEXT:
{soo_text[:6000]}

RETURN ONLY THIS JSON STRUCTURE - NO OTHER TEXT:

[
  {{"System": "ASHP-1", "Equipment_Type": "Air Source Heat Pump", "Control_Approach": "DDC", "Control_Points": "Compressor, fan speed, water temp", "Integration": "Hardwired 8 pts, BACnet 2 pts", "Key_Features": "Staging, freeze protection"}},
  {{"System": "DOAS-1M-1", "Equipment_Type": "Dedicated Outside Air System", "Control_Approach": "DDC Controller", "Control_Points": "Fan start/stop, enthalpy, dampers", "Integration": "BACnet network", "Key_Features": "Demand reset, enthalpy control"}}
]

RULES:
- Return JSON array ONLY
- One object per HVAC system/equipment
- Extract: System name, Equipment type, Control approach, Control points, Integration method, Key features
- NO project info, NO general requirements
- START with [ and END with ]
- NO markdown, NO code blocks, NO extra text"""
    
    return prompt


def generate_pointlist_prompt(project_name, soo_text, takeoff_equip=None):
    """Generate prompt for Point List extraction."""
    
    prompt = f"""EXTRACT BMS CONTROL POINTS FROM THIS SOO.

PROJECT: {project_name}

SOO TEXT:
{soo_text[:6000]}

RETURN ONLY THIS JSON ARRAY - NO OTHER TEXT:

[
  {{"Panel Name": "MER-DDC-1", "Equipment": "ASHP-1", "Point name": "Compressor Enable", "Control Device": "Honeywell PLC", "AI": "", "BI": "", "AO": "", "BO": "x", "Serial Pt": "", "Terms": "OUT-1", "Remarks": "Enable signal"}},
  {{"Panel Name": "MER-DDC-1", "Equipment": "ASHP-1", "Point name": "Supply Water Temp", "Control Device": "Honeywell PLC", "AI": "x", "BI": "", "AO": "", "BO": "", "Serial Pt": "", "Terms": "AI-1", "Remarks": "Sensor input"}}
]

RULES:
- Return JSON array ONLY
- ONE ROW PER POINT (not per equipment)
- Extract EVERY control point mentioned
- Panel Name: Infer from system (e.g., MER-DDC-1)
- Equipment: System tag (ASHP-1, DOAS-1M-1)
- Point name: Exact name from SOO
- Control Device: Honeywell, Siemens, Manufacturer, etc
- I/O: Mark with "x" if present (AI, BI, AO, BO, Serial Pt)
- Terms: Terminal/connection info
- Remarks: Notes from SOO
- START with [ and END with ]
- NO markdown, NO extra text"""
    
    return prompt


def generate_appendix_prompt(project_name, soo_text, main_equipment):
    """Generate prompt for Appendix points (special sequences)."""
    
    main_str = ", ".join(main_equipment) if main_equipment else ""
    
    prompt = f"""EXTRACT SPECIAL/APPENDIX POINTS FROM THIS SOO.

PROJECT: {project_name}
Main equipment: {main_str}

SOO TEXT:
{soo_text[:6000]}

RETURN ONLY THIS JSON ARRAY - NO OTHER TEXT:

[
  {{"Panel Name": "MER-DDC-1", "Equipment": "PFSP-1M-1", "Point name": "Post-Fire Smoke Purge Enable", "Control Device": "Fire Alarm Interface", "AI": "", "BI": "", "AO": "", "BO": "x", "Serial Pt": "", "Terms": "OUT-5", "Remarks": "Fire safety"}}
]

APPENDIX INCLUDES ONLY:
- Post-fire smoke purge sequences
- Life safety pressurization
- Emergency sequences
- Future expansion points
- DO NOT include main HVAC equipment already listed

RULES:
- Return JSON array ONLY
- Same format as main point list
- START with [ and END with ]
- NO markdown, NO extra text"""
    
    return prompt


def generate_important_notes_prompt(project_name, soo_text):
    """Generate prompt for Important Notes (estimation)."""
    
    prompt = f"""EXTRACT KEY ESTIMATION NOTES FROM THIS SOO.

PROJECT: {project_name}

SOO TEXT:
{soo_text[:6000]}

RETURN ONLY THIS JSON - NO OTHER TEXT:

{{
  "ddc_complexity": ["87 hardwired I/O points", "12 BACnet points", "3 panels total"],
  "special_integrations": ["Fire alarm interface required", "Manufacturer ERV integration"],
  "control_sequences": ["Modular ASHP staging", "Enthalpy wheel modulation"],
  "safety_interlocks": ["Freeze protection at 40F", "Low pressure interlock"],
  "commissioning": ["Factory startup required", "Sensor calibration needed"],
  "lead_times": ["Custom panels 8 weeks", "Special sensors 4-6 weeks"],
  "client_requirements": ["Pre-approval of sequences", "3-day training required"]
}}

Extract for each category:
- ddc_complexity: I/O counts, wiring, panel info, protocols
- special_integrations: Fire alarm, manufacturer, third-party
- control_sequences: Staging, reset logic, multi-zone
- safety_interlocks: Freeze, emergency, alarms
- commissioning: Startup, balancing, testing, training
- lead_times: Custom hardware, sensors, materials
- client_requirements: Approvals, training, warranty

RULES:
- START with {{ and END with }}
- NO markdown, NO extra text"""
    
    return prompt


def parse_pointlist_response(raw_response):
    """Parse point list JSON array - handles markdown and variations."""
    if not raw_response:
        return []
    
    try:
        text = str(raw_response).strip()
        
        # Remove markdown code blocks
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        
        # Find JSON array
        start = text.find("[")
        end = text.rfind("]")
        
        if start == -1 or end == -1:
            return []
        
        json_str = text[start:end+1]
        result = json.loads(json_str)
        
        return result if isinstance(result, list) else []
    except:
        return []


def parse_notes_response(raw_response):
    """Parse notes JSON object - handles markdown and variations."""
    if not raw_response:
        return {}
    
    try:
        text = str(raw_response).strip()
        
        # Remove markdown code blocks
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        
        # Find JSON object
        start = text.find("{")
        end = text.rfind("}")
        
        if start == -1 or end == -1:
            return {}
        
        json_str = text[start:end+1]
        result = json.loads(json_str)
        
        return result if isinstance(result, dict) else {}
    except:
        return {}


def parse_overview_response(raw_response):
    """Parse overview response - MOST FLEXIBLE."""
    if not raw_response:
        return {"overview": []}
    
    try:
        text = str(raw_response).strip()
        
        # Remove markdown
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        
        # Try to find and parse JSON
        start = text.find("[")
        end = text.rfind("]")
        
        if start != -1 and end != -1:
            # Found array format
            json_str = text[start:end+1]
            result = json.loads(json_str)
            if isinstance(result, list):
                return {"overview": result}
        
        # Try object format
        start = text.find("{")
        end = text.rfind("}")
        
        if start != -1 and end != -1:
            json_str = text[start:end+1]
            result = json.loads(json_str)
            if isinstance(result, dict):
                # Check if it has "overview" key
                if "overview" in result:
                    overview_data = result["overview"]
                    if isinstance(overview_data, list):
                        return {"overview": overview_data}
                    elif isinstance(overview_data, dict) and "overview" in overview_data:
                        return overview_data
                # If not, treat entire result as overview list
                return {"overview": [result] if result else []}
        
        return {"overview": []}
    except:
        return {"overview": []}
