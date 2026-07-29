"""
soo_extractor.py - ULTRA-ROBUST VERSION
Handles markdown-wrapped JSON and various Claude response formats
"""

import json
import re


def generate_overview_prompt(project_name, soo_text):
    """Generate prompt for SOO Overview."""
    prompt = f"""Extract overview from SOO. Return ONLY JSON.

PROJECT: {project_name}

SOO:
{soo_text[:5000]}

{{
  "overview": [
    {{"System": "ASHP-1", "Equipment_Type": "Heat Pump", "Control_Approach": "DDC", "Control_Points": "Points", "Integration": "BACnet", "Key_Features": "Features"}}
  ]
}}"""
    return prompt


def generate_pointlist_prompt(project_name, soo_text, takeoff_equip=None):
    """Generate prompt for Point List."""
    prompt = f"""Extract point list from SOO. Return ONLY JSON array.

PROJECT: {project_name}

SOO:
{soo_text[:5000]}

[
  {{"Panel Name": "MER", "Equipment": "ASHP-1", "Point name": "Point", "Control Device": "PLC", "AI": "", "BI": "", "AO": "", "BO": "x", "Serial Pt": "", "Terms": "OUT", "Remarks": "Note"}}
]"""
    return prompt


def generate_appendix_prompt(project_name, soo_text, main_equipment):
    """Generate prompt for Appendix."""
    main_str = ", ".join(main_equipment) if main_equipment else ""
    prompt = f"""Extract appendix points from SOO. Return ONLY JSON array.

PROJECT: {project_name}
Main: {main_str}

SOO:
{soo_text[:5000]}

[
  {{"Panel Name": "MER", "Equipment": "PFSP", "Point name": "Fire", "Control Device": "FA", "AI": "", "BI": "", "AO": "", "BO": "x", "Serial Pt": "", "Terms": "OUT", "Remarks": "Fire"}}
]"""
    return prompt


def generate_important_notes_prompt(project_name, soo_text):
    """Generate prompt for Important Notes."""
    prompt = f"""Extract notes from SOO. Return ONLY JSON.

PROJECT: {project_name}

SOO:
{soo_text[:5000]}

{{
  "ddc_complexity": ["87 hardwired I/O"],
  "special_integrations": ["Fire alarm"],
  "control_sequences": ["Staging"],
  "safety_interlocks": ["Freeze"],
  "commissioning": ["Startup"],
  "lead_times": ["8 weeks"],
  "client_requirements": ["Training"]
}}"""
    return prompt


def parse_pointlist_response(raw_response):
    """Parse point list - handles markdown and various formats."""
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
    """Parse notes - handles markdown and various formats."""
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
