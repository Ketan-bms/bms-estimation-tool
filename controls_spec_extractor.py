"""
controls_spec_extractor.py
Extract from Controls Spec:
1. Important Notes (requirements, decisions, key specs)
2. Questions (ambiguous/unclear items)
"""

import json


def generate_notes_prompt(project_name, spec_text):
    """Generate prompt for Important Notes from Controls Spec."""
    
    prompt = f"""You are a senior BMS controls engineer reviewing a specification document.
Extract important notes for project execution.

PROJECT: {project_name}

CONTROLS SPECIFICATION:
{spec_text}

EXTRACT THESE CATEGORIES (as separate lists):

1. DEVICE SELECTION & APPROVAL:
   - Specific approved manufacturers/models
   - Pre-approval requirements
   - Alternates allowed or not
   - Custom configurations required
   - Equipment restrictions

2. CONTROL LOGIC & SEQUENCES:
   - Required control strategies
   - Setpoint ranges and limits
   - Emergency procedures
   - Override capabilities
   - Special operating modes

3. WIRING & TERMINATION:
   - Wire types/ratings (plenum-rated, shielded, etc.)
   - Termination standards
   - Cable labeling requirements
   - Conduit specifications
   - Grounding/bonding requirements

4. COMMUNICATION & NETWORK:
   - Protocol requirements (BACnet, Modbus, LON, etc.)
   - Network architecture
   - Integration points with other systems
   - Communication testing requirements

5. COMMISSIONING & TESTING:
   - Required test procedures
   - Performance verification
   - Calibration requirements
   - Documentation standards
   - As-built requirements

6. MAINTENANCE & SUPPORT:
   - Training requirements
   - Spare parts provisions
   - Warranty terms
   - Support/maintenance contract

7. COMPLIANCE & STANDARDS:
   - Codes and standards referenced
   - Energy code requirements
   - Safety certifications needed
   - Special compliance items

8. SPECIAL REQUIREMENTS:
   - System redundancy
   - Failover/backup procedures
   - Data logging/trending
   - Remote access/monitoring
   - Special interfaces

OUTPUT: Return JSON:

{{
  "device_selection": ["requirement 1", "requirement 2", ...],
  "control_logic": ["strategy 1", "requirement 1", ...],
  "wiring_termination": ["requirement 1", ...],
  "communication_network": ["requirement 1", ...],
  "commissioning_testing": ["requirement 1", ...],
  "maintenance_support": ["requirement 1", ...],
  "compliance_standards": ["requirement 1", ...],
  "special_requirements": ["requirement 1", ...]
}}

CRITICAL: Start with {{ and end with }}. No markdown.
Focus on actionable requirements that affect design and estimation."""
    
    return prompt


def generate_questions_prompt(project_name, spec_text):
    """Generate prompt for Questions/Ambiguities from Controls Spec."""
    
    prompt = f"""You are a senior BMS controls engineer reviewing a specification document.
Identify unclear, ambiguous, or missing information that needs clarification.

PROJECT: {project_name}

CONTROLS SPECIFICATION:
{spec_text}

IDENTIFY QUESTIONS IN THESE CATEGORIES:

1. SCOPE AMBIGUITY:
   - Unclear device quantities or locations
   - Unclear control point definitions
   - Missing system descriptions

2. SPECIFICATION CONFLICTS:
   - Contradictory requirements
   - Unclear sequencing logic
   - Conflicting device selections

3. MISSING INFORMATION:
   - Incomplete specifications
   - Missing alarm thresholds
   - Undefined setpoints or parameters

4. COMMISSIONING CLARITY:
   - Unclear testing procedures
   - Undefined acceptance criteria
   - Missing startup procedures

5. INTERFACE QUESTIONS:
   - Unclear integration with other systems
   - Missing connection specifications
   - Undefined data exchange protocols

6. APPROVAL/AUTHORITY:
   - Unclear approval process
   - Undefined change order procedures
   - Missing submission requirements

7. TECHNICAL DETAILS:
   - Unclear control logic
   - Missing failure mode definitions
   - Undefined operating ranges

OUTPUT: Return JSON:

{{
  "questions": [
    {{
      "category": "SCOPE AMBIGUITY",
      "question": "Are the unit heaters (EUH) included in the BMS scope? SOO shows 12 units but specification doesn't reference them.",
      "reference": "Section 3.1, Drawing M-100"
    }},
    {{
      "category": "MISSING INFORMATION",
      "question": "What are the setpoints for low temperature alarm on ASHP? Specification references freeze protection but doesn't specify trigger temperature.",
      "reference": "Section 3.1 ASHP sequence"
    }},
    ...
  ]
}}

CRITICAL: Start with {{ and end with }}. No markdown.
List questions that would be asked by a competent BMS engineer reviewing for bids/design."""
    
    return prompt


def parse_overview_response(raw_response):
    """Parse overview JSON response."""
    try:
        text = raw_response.strip()
        s = text.find("{")
        e = text.rfind("}")
        if s == -1 or e == -1:
            raise ValueError("No JSON found")
        return json.loads(text[s:e+1])
    except Exception as exc:
        return {"error": str(exc), "raw": raw_response[:200]}


def parse_pointlist_response(raw_response):
    """Parse point list JSON array response."""
    try:
        text = raw_response.strip()
        s = text.find("[")
        e = text.rfind("]")
        if s == -1 or e == -1:
            raise ValueError("No array found")
        rows = json.loads(text[s:e+1])
        if not isinstance(rows, list):
            raise ValueError("Expected array")
        return rows
    except Exception as exc:
        return []


def parse_notes_response(raw_response):
    """Parse important notes JSON response."""
    try:
        text = raw_response.strip()
        s = text.find("{")
        e = text.rfind("}")
        if s == -1 or e == -1:
            raise ValueError("No JSON found")
        return json.loads(text[s:e+1])
    except Exception as exc:
        return {"error": str(exc)}


def parse_questions_response(raw_response):
    """Parse questions JSON response."""
    try:
        text = raw_response.strip()
        s = text.find("{")
        e = text.rfind("}")
        if s == -1 or e == -1:
            raise ValueError("No JSON found")
        data = json.loads(text[s:e+1])
        return data.get("questions", [])
    except Exception as exc:
        return []


if __name__ == "__main__":
    print("Controls Spec Extractor Module Ready")
    print("=" * 70)
    print("\nFunctions:")
    print("  1. generate_notes_prompt() - Extract important notes")
    print("  2. generate_questions_prompt() - Extract questions/ambiguities")
    print("  3. parse_notes_response() - Parse notes JSON")
    print("  4. parse_questions_response() - Parse questions JSON")
