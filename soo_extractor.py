"""
soo_extractor.py
Complete SOO extraction module - NO ERRORS
"""

import json
import re


def generate_overview_prompt(project_name, soo_text):
    """Generate prompt for SOO Overview."""
    prompt = f"""Extract overview from SOO.
PROJECT: {project_name}
SOO TEXT:
{soo_text[:5000]}

Return JSON:
{{
  "overview": [
    {{"System": "ASHP-1", "Equipment_Type": "Heat Pump", "Control_Approach": "DDC", "Control_Points": "Points", "Integration": "BACnet", "Key_Features": "Features"}}
  ]
}}
"""
    return prompt


def generate_pointlist_prompt(project_name, soo_text):
    """Generate prompt for Point List."""
    prompt = f"""Extract point list from SOO.
PROJECT: {project_name}
SOO TEXT:
{soo_text[:5000]}

Return JSON array:
[
  {{"Panel Name": "MER", "Equipment": "ASHP-1", "Point name": "Compressor", "Control Device": "PLC", "AI": "", "BI": "", "AO": "", "BO": "x", "Serial Pt": "", "Terms": "OUT-1", "Remarks": "Note"}}
]
"""
    return prompt


def generate_appendix_prompt(project_name, soo_text, main_equipment):
    """Generate prompt for Appendix."""
    prompt = f"""Extract appendix points from SOO.
PROJECT: {project_name}
SOO TEXT:
{soo_text[:5000]}

Return JSON array:
[
  {{"Panel Name": "MER", "Equipment": "PFSP", "Point name": "Fire Safety", "Control Device": "FA", "AI": "", "BI": "", "AO": "", "BO": "x", "Serial Pt": "", "Terms": "OUT-5", "Remarks": "Fire"}}
]
"""
    return prompt


def generate_important_notes_prompt(project_name, soo_text):
    """Generate prompt for Important Notes."""
    prompt = f"""Extract estimation notes from SOO.
PROJECT: {project_name}
SOO TEXT:
{soo_text[:5000]}

Return JSON:
{{
  "ddc_complexity": ["87 hardwired I/O"],
  "special_integrations": ["Fire alarm"],
  "control_sequences": ["Staging logic"],
  "safety_interlocks": ["Freeze protection"],
  "commissioning": ["Factory startup"],
  "lead_times": ["8 weeks panels"],
  "client_requirements": ["Pre-approval"]
}}
"""
    return prompt


def parse_pointlist_response(raw_response):
    """Parse point list from Claude response."""
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
    """Parse notes from Claude response."""
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
