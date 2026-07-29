"""
soo_extractor.py - INTELLIGENT AI-DRIVEN SCOPE ANALYSIS
Uses AI intelligence to analyze, understand, and create dynamic scopes
Not template-based - produces unique insights each time
"""

import json
import re


def generate_intelligent_analysis_prompt(project_name, soo_text):
    """AI analyzes SOO intelligently and identifies key scope elements."""
    
    prompt = f"""You are an expert BMS controls engineer analyzing a Sequence of Operations document.
Read and UNDERSTAND this SOO deeply. Think critically about:
- What systems are most complex?
- What sequences are interdependent?
- What are the critical control points?
- What safety sequences must work perfectly?
- What are the unusual or challenging requirements?
- What could cause problems if not done right?

PROJECT: {project_name}

FULL SEQUENCE OF OPERATIONS:
{soo_text}

ANALYZE this SOO and create an INTELLIGENT SCOPE that shows your understanding:

Return ONLY valid JSON:

{{
  "analysis": {{
    "project_overview": "Your one-paragraph summary of what this building controls",
    "system_complexity_ranking": [
      {{"system": "ASHP or cooling towers", "complexity_reason": "Why it's most complex"}},
      {{"system": "Next most complex", "complexity_reason": "Why"}}
    ],
    "critical_sequences": [
      "Most important sequence 1 and why",
      "Most important sequence 2 and why"
    ],
    "interdependencies": [
      "How system A depends on system B",
      "How system C triggers system D"
    ],
    "risk_areas": [
      "What could fail and cause major problems",
      "What sequences are safety-critical"
    ],
    "unusual_requirements": [
      "Non-standard control logic in this project",
      "Integration requirements that are tricky"
    ],
    "estimation_drivers": [
      "What will drive costs (complexity, integration, customization)",
      "What requires special expertise"
    ]
  }},
  "estimated_scope": {{
    "estimated_total_points": "Your estimate based on analysis",
    "estimated_hardwired_io": "Your estimate of hardwired points",
    "estimated_network_points": "Your estimate of network points",
    "primary_integrations": ["Integration 1", "Integration 2"],
    "special_skills_required": ["Skill 1", "Skill 2"],
    "timeline_drivers": ["What will take longest"]
  }}
}}

Think critically. Don't just list data - show your understanding of:
- How this building actually operates
- What makes this controls project unique
- What needs to work perfectly for occupant comfort
- What could cause operational problems

Your analysis should demonstrate deep comprehension, not surface-level extraction."""
    
    return prompt


def generate_control_logic_analysis_prompt(project_name, soo_text):
    """AI analyzes the actual control logic and sequencing intelligence."""
    
    prompt = f"""You are a controls logic expert. Analyze the CONTROL LOGIC in this SOO.
Focus on:
- What is the INTELLIGENCE behind each system?
- How do systems talk to each other?
- What happens during mode transitions (occupied→unoccupied→emergency)?
- Where is adaptive logic (VFD modulation, lead-lag staging)?
- What's automated vs manual?
- Where is redundancy or safety built in?

PROJECT: {project_name}

FULL SEQUENCE OF OPERATIONS:
{soo_text}

ANALYZE the control logic intelligence:

Return ONLY valid JSON:

{{
  "control_logic_analysis": {{
    "automation_level": "What percentage is automated vs manual?",
    "adaptive_sequences": [
      "System A adapts to X condition by doing Y",
      "System B uses Z logic to optimize operation"
    ],
    "mode_transitions": {{
      "occupied_mode": "What happens when building occupies",
      "unoccupied_mode": "What happens when building empties",
      "emergency_mode": "What happens in fire/emergency",
      "startup_sequence": "What's the order of equipment startup",
      "shutdown_sequence": "What's the order of equipment shutdown"
    }},
    "inter_system_logic": [
      "How does chiller talk to cooling tower?",
      "How does outside air station control heating/cooling?",
      "How do heat pumps stage with main equipment?"
    ],
    "redundancy_safety": [
      "What's redundant for safety?",
      "What has backup systems?",
      "What has interlocks?"
    ],
    "optimization_strategies": [
      "Lead-lag staging for load sharing",
      "VFD modulation for energy efficiency",
      "Demand reset for setpoint adjustment"
    ],
    "complexity_hotspots": [
      "Most complex interaction 1 and why",
      "Most complex interaction 2 and why"
    ]
  }},
  "control_challenges": {{
    "hardest_sequences": ["Sequence 1", "Sequence 2"],
    "integration_challenges": ["Challenge 1", "Challenge 2"],
    "commissioning_risks": ["Risk 1", "Risk 2"],
    "operational_insights": ["How this building's controls are unique"]
  }}
}}

Demonstrate deep understanding of control system intelligence, not just listing points."""
    
    return prompt


def generate_scope_insight_prompt(project_name, soo_text):
    """AI generates scope insights based on intelligent analysis."""
    
    prompt = f"""You are a BMS controls engineer creating a scope estimate.
Analyze this SOO and create an INSIGHTFUL scope that explains:
- What drives cost/complexity
- What requires special skills
- What determines timeline
- What could impact profitability

PROJECT: {project_name}

FULL SEQUENCE OF OPERATIONS:
{soo_text}

Create an intelligent scope estimate:

Return ONLY valid JSON:

{{
  "scope_insights": {{
    "what_makes_this_project_unique": "How is this project different from standard buildings?",
    "cost_drivers": [
      "Driver 1: Why it will cost more",
      "Driver 2: Why complexity increases costs"
    ],
    "timeline_drivers": [
      "Task 1: Why it will take time",
      "Task 2: What's on the critical path"
    ],
    "skill_requirements": [
      "Expertise needed 1",
      "Expertise needed 2"
    ],
    "profitability_factors": [
      "What helps margin",
      "What threatens margin"
    ]
  }},
  "smart_scope": {{
    "systems_count": "How many distinct systems",
    "total_estimated_points": "AI estimate based on analysis",
    "hardwired_io_estimate": "Based on system complexity",
    "network_points_estimate": "Based on integration needs",
    "labor_estimate": "Rough hours needed",
    "risk_mitigation": [
      "What could go wrong and mitigation"
    ],
    "value_adds": [
      "What could add value or efficiency"
    ]
  }}
}}

This should read like an experienced engineer's honest assessment, not a template."""
    
    return prompt


def generate_custom_questions_prompt(project_name, soo_text, question):
    """AI answers custom questions about the SOO intelligently."""
    
    prompt = f"""You are a BMS controls expert reviewing a Sequence of Operations.
Answer this specific question intelligently:

QUESTION: {question}

PROJECT: {project_name}

FULL SEQUENCE OF OPERATIONS:
{soo_text}

Analyze the SOO and provide a thorough, insightful answer to the question above.
Consider context, interdependencies, and practical implications.

Return your analysis and insights directly - demonstrate deep understanding."""
    
    return prompt


def parse_json_response(raw_response):
    """Parse JSON response from Claude analysis."""
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
            return {"raw_analysis": raw_response}
        
        json_str = text[start:end+1]
        result = json.loads(json_str)
        
        return result if isinstance(result, dict) else {"raw_analysis": raw_response}
    except:
        return {"raw_analysis": raw_response}
