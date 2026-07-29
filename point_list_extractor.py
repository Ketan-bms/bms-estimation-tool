"""
point_list_extractor.py
Generate BMS point lists with columns: Panel Name, Equipment, Point Name, Control Device, AI, BI, AO, BO, Serial Pt, Terms, Remarks.
AI extracts all fields from SOO; user refines in editor.
"""

import json
import re
from io import BytesIO


def infer_io_type(point_name, description=""):
    """
    Infer I/O type from point name/description.
    Returns dict with keys: AI, BI, AO, BO, Serial_Pt
    Each key has value 'x' if inferred, '' otherwise.
    """
    result = {"AI": "", "BI": "", "AO": "", "BO": "", "Serial_Pt": ""}
    
    text = (point_name + " " + description).lower()
    
    # Binary Output patterns (commands, control)
    bo_patterns = [
        r"start\b", r"stop\b", r"enable\b", r"disable\b",
        r"open\b", r"close\b", r"signal\b", r"command\b",
        r"valve control", r"damper control", r"fan control",
        r"pump control", r"alarm reset", r"interlock",
        r"energize", r"de-energize"
    ]
    
    # Binary Input patterns (status, switches, alarms)
    bi_patterns = [
        r"status\b", r"run status", r"switch\b",
        r"alarm\b", r"fault\b", r"indication\b",
        r"feedback\b", r"end switch", r"proof of operation",
        r"low limit", r"high limit", r"safety",
        r"closed indication", r"open indication"
    ]
    
    # Analog Output patterns (modulation, setpoints)
    ao_patterns = [
        r"modulation\b", r"speed control", r"vfd",
        r"setpoint\b", r"duct position", r"damper position",
        r"valve position", r"percent\b", r"0-10v", r"4-20ma"
    ]
    
    # Analog Input patterns (sensors, readings)
    ai_patterns = [
        r"temperature\b", r"humidity\b", r"pressure\b",
        r"flow\b", r"airflow\b", r"co2\b", r"sensor\b",
        r"reading\b", r"dry bulb", r"wet bulb", r"dew point",
        r"differential", r"static", r"gauge", r"level"
    ]
    
    # Serial/Network patterns
    serial_patterns = [
        r"bacnet\b", r"modbus\b", r"lon\b", r"ms/tp",
        r"serial\b", r"network\b", r"communication\b", r"interface"
    ]
    
    if any(re.search(p, text) for p in bo_patterns):
        result["BO"] = "x"
    if any(re.search(p, text) for p in bi_patterns):
        result["BI"] = "x"
    if any(re.search(p, text) for p in ao_patterns):
        result["AO"] = "x"
    if any(re.search(p, text) for p in ai_patterns):
        result["AI"] = "x"
    if any(re.search(p, text) for p in serial_patterns):
        result["Serial_Pt"] = "x"
    
    # If no I/O type inferred, default to AI (sensor reading)
    if not any(result.values()):
        result["AI"] = "x"
    
    return result


def generate_point_list_prompt(project_name, soo_text, takeoff_equip=None):
    """
    Generate Claude prompt for BMS point list extraction.
    
    Args:
        project_name: Project name (e.g., "West 34th Street Hotel")
        soo_text: Extracted SOO text (8000+ chars recommended)
        takeoff_equip: List of equipment from takeoff (optional, for context)
    
    Returns:
        Prompt string ready for Claude API
    """
    
    # Build equipment context if available
    equip_context = ""
    if takeoff_equip:
        from collections import Counter
        equip_counts = Counter(e.get("system", "Unknown") for e in takeoff_equip)
        equip_list = "; ".join(f"{v}× {k}" for k, v in equip_counts.most_common(15))
        equip_context = f"\n\nKnown equipment from takeoff: {equip_list}\nUse these tags where they appear in the SOO."
    
    example_row = {
        "Panel Name": "MER-DDC-1",
        "Equipment": "ASHP-1",
        "Point Name": "Supply Fan Start/Stop",
        "Control Device": "Honeywell PLC",
        "AI": "",
        "BI": "",
        "AO": "",
        "BO": "x",
        "Serial_Pt": "",
        "Terms": "OUT-1, OUT-2",
        "Remarks": "Energize to enable; de-energize to stop"
    }
    
    prompt = f"""You are a senior BMS controls engineer extracting a point list from an SOO (Sequence of Operations).

PROJECT: {project_name}{equip_context}

SEQUENCE OF OPERATIONS:
{soo_text}

OUTPUT RULES:
1. Return a JSON array of objects, one row per BMS point (NOT per device)
2. Use EXACTLY these column names (no extras):
   - Panel Name: Name/ID of control panel where point is wired (e.g., MER-DDC-1, AHU-1-CTL)
   - Equipment: Device/system tag (e.g., ASHP-1, DOAS-1M-1, FCU-SC-5)
   - Point Name: Exact point description from SOO (e.g., "Supply Fan Start/Stop", "Supply Air Temperature")
   - Control Device: Manufacturer/type (e.g., "Honeywell PLC", "Siemens VAV Box", "BACnet Interface")
   - AI, BI, AO, BO, Serial_Pt: Leave blank ("") or mark with "x" if present
   - Terms: Terminal/connection designations (e.g., "OUT-1, OUT-2", "AI-03")
   - Remarks: Notes on operation or special handling

3. DO NOT skip points. Extract EVERY point table in the SOO:
   - All I/O (start/stop, status, valves, sensors, alarms, interlocks)
   - Cover every system mentioned (ASHP, DOAS, AHU, ERV, FCU, VAV, ACU, HWC, CHWP, PHWP, SHWP, PFHX, FOP, GX, EF, EF, BT, GFU, etc.)

4. Each system typically has:
   - Fan start/stop (BO)
   - Fan status (BI)
   - Fan speed control (AO)
   - Temperature sensors (AI)
   - Valve modulation (AO or BO)
   - Pressure/differential sensors (AI)
   - Alarms (BI)
   - Interlocks (BO or BI)

5. I/O Type inference rules (AI will auto-mark based on point name):
   - BO (Binary Output): start, stop, enable, disable, open, close, valve control, damper control, command, signal
   - BI (Binary Input): status, alarm, fault, indication, feedback, end switch, limit, safety
   - AO (Analog Output): modulation, speed control, position control, setpoint
   - AI (Analog Input): temperature, humidity, pressure, flow, sensor, reading
   - Serial_Pt: BACnet, Modbus, network, communication interface

6. For Panel Name: Use control panel prefix if mentioned in SOO (e.g., "MER-DDC-1" for MER equipment).
   If no specific panel mentioned, infer from system (e.g., "AHU-1-CTL" for AHU-1 points).

7. For Control Device: Identify from SOO (Honeywell PLC, Siemens Controller, BACnet Gateway, etc.)
   If not specified, default to "Honeywell" or vendor mentioned in project scope.

8. For Terms: Extract terminal/connection info if SOO specifies (e.g., "OUT-1, OUT-2").
   If not available, leave blank.

CRITICAL:
- Start response with [ and end with ]. No markdown, no explanation, no code fences.
- One row per point. Do NOT summarize or combine rows.
- DO NOT add any fields beyond the 11 listed above.

Example row format:
{json.dumps([example_row])}

Now extract ALL points from the SOO above and return as a JSON array:"""
    
    return prompt


def parse_point_list_response(raw_response):
    """
    Parse Claude's JSON response and apply I/O type inference.
    
    Args:
        raw_response: Raw string response from Claude
    
    Returns:
        List of point dicts with I/O types inferred and filled
    """
    
    # Extract JSON array from response
    text = raw_response.strip()
    
    # Try to find array bounds
    s = text.find("[")
    e = text.rfind("]")
    
    if s == -1 or e == -1 or e <= s:
        raise ValueError(f"No JSON array found in response.\nRaw: {text[:200]}")
    
    json_str = text[s:e+1]
    
    try:
        rows = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}\nSnippet: {json_str[:300]}")
    
    if not isinstance(rows, list):
        raise ValueError(f"Expected JSON array, got {type(rows)}")
    
    if not rows:
        raise ValueError("Empty point list returned")
    
    # Ensure all columns present and apply I/O inference
    columns = ["Panel Name", "Equipment", "Point Name", "Control Device", 
               "AI", "BI", "AO", "BO", "Serial_Pt", "Terms", "Remarks"]
    
    for row in rows:
        # Fill missing columns
        for col in columns:
            if col not in row:
                row[col] = ""
        
        # Infer I/O types
        point_name = row.get("Point Name", "")
        remarks = row.get("Remarks", "")
        io_types = infer_io_type(point_name, remarks)
        
        # Only apply inference if AI didn't already mark (user may have manually set)
        for io_key in ["AI", "BI", "AO", "BO", "Serial_Pt"]:
            if not row.get(io_key) or row[io_key] == "":
                row[io_key] = io_types[io_key]
        
        # Clean up: ensure only 'x' or empty string
        for io_key in ["AI", "BI", "AO", "BO", "Serial_Pt"]:
            val = str(row[io_key]).strip().lower()
            row[io_key] = "x" if val in ("x", "1", "yes", "true") else ""
    
    return rows


if __name__ == "__main__":
    # Test the prompt generation and parsing
    print("Point List Extractor Module")
    print("=" * 70)
    
    # Example SOO snippet
    sample_soo = """
    ASHP-1 – Air Source Heat Pump
    - Supply Fan Start/Stop: Enable/disable compressor and fans
    - Supply Fan Status: Proof of operation; alarm on failure
    - Supply Fan Speed Control: VFD modulation 0-10V
    - Leaving Water Temperature: Sensor input to DDC (°F)
    - Low Temperature Alarm: Safety shutdown at <35°F
    - BACnet Interface: Network communication to main DDC
    
    DOAS-1M-1 – Dedicated Outdoor Air System
    - Supply Fan Start/Stop: Enable/disable supply fan motor
    - Return/Exhaust Fan Status: Feedback from fan starter
    - Outdoor Air Damper Control: Proportional position modulation
    - Mixed Air Temperature Sensor: Input 0-10V (°F)
    - Supply Air Pressure: Differential switch indication
    - Enthalpy Wheel Modulation: Speed control output 0-10V
    """
    
    prompt = generate_point_list_prompt("West 34th Street Hotel", sample_soo)
    
    print("\nGenerated Prompt (first 500 chars):")
    print(prompt[:500])
    
    print("\n✅ Module ready for integration into app.py")
