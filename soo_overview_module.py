"""
soo_overview_module.py
Independent SOO Overview with 3 tabs: Summary table, System-wise breakdown, Labor estimates
"""

import json
import pandas as pd
from collections import defaultdict


def extract_soo_to_overview(soo_text, takeoff_equip=None):
    """
    Parse SOO and extract overview data.
    Returns: summary_df, system_breakdown_df, labor_df
    """
    
    # This would be enhanced with Claude for real extraction
    # For now, returns structured placeholders
    
    summary_data = {
        "System": ["ASHP", "DOAS", "AHU", "FCU", "VAV", "ERV", "CHWP", "PHWP", "EF"],
        "Qty": [3, 3, 2, 8, 60, 2, 3, 3, 5],
        "Description": [
            "Air Source Heat Pump with staging",
            "Dedicated Outdoor Air System",
            "Air Handling Units",
            "Fan Coil Units (2-pipe, 2-speed)",
            "Variable Air Volume boxes",
            "Energy Recovery Units",
            "Chilled Water Pumps (Secondary)",
            "Primary Hot Water Pumps",
            "Exhaust Fans (General + specialized)"
        ],
        "SOO Section": [
            "Section 3.1",
            "Section 3.2",
            "Section 3.3",
            "Section 3.4",
            "Section 3.5",
            "Section 3.6",
            "Section 4.1",
            "Section 4.2",
            "Section 5.1"
        ]
    }
    
    system_breakdown = {
        "System": ["ASHP-1", "ASHP-2", "ASHP-3", "DOAS-1M-1", "DOAS-12-1", "DOAS-12-2"],
        "Equipment": ["Air Source Heat Pump", "Air Source Heat Pump", "Air Source Heat Pump", 
                     "DOAS with ERV", "DOAS with ERV", "DOAS with ERV"],
        "Compressor Start/Stop": ["BO", "BO", "BO", "", "", ""],
        "Compressor Status": ["BI", "BI", "BI", "", "", ""],
        "Supply Fan Control": ["AO", "AO", "AO", "AO", "AO", "AO"],
        "Temperature Sensors": ["AI", "AI", "AI", "AI", "AI", "AI"],
        "Enthalpy Wheel": ["", "", "", "AO", "AO", "AO"],
        "Alarms": ["BI", "BI", "BI", "BI", "BI", "BI"]
    }
    
    labor_data = {
        "System": ["ASHP", "DOAS", "AHU", "FCU", "VAV", "ERV"],
        "Equipment Count": [3, 3, 2, 8, 60, 2],
        "Points/Equipment": [8, 15, 12, 6, 3, 12],
        "Total Points": [24, 45, 24, 48, 180, 24],
        "Engineering (hrs)": [12, 22.5, 12, 24, 90, 12],
        "Programming (hrs)": [24, 45, 24, 48, 180, 24],
        "Integration (hrs)": [12, 22.5, 12, 24, 90, 12],
        "Graphics (hrs)": [12, 22.5, 12, 24, 90, 12],
        "Startup (hrs)": [12, 22.5, 12, 24, 90, 12]
    }
    
    return (
        pd.DataFrame(summary_data),
        pd.DataFrame(system_breakdown),
        pd.DataFrame(labor_data)
    )


def generate_overview_prompt(project_name, soo_text):
    """Generate Claude prompt for SOO overview extraction."""
    
    prompt = f"""You are a senior BMS engineer. Extract an overview from this SOO.

PROJECT: {project_name}

SEQUENCE OF OPERATIONS:
{soo_text[:8000]}

OUTPUT: Return a JSON object with three sections:

1. SUMMARY_TABLE: Array of systems with: System, Qty, Description, SOO_Section
2. SYSTEM_BREAKDOWN: Array of equipment with control I/O points by system
3. LABOR_ESTIMATE: Array with system name, equipment count, point count, hours by phase

Format as JSON with these exact keys:
{{
  "summary": [
    {{"System": "ASHP", "Qty": 3, "Description": "...", "SOO_Section": "3.1"}},
    ...
  ],
  "system_breakdown": [
    {{"System": "ASHP-1", "Equipment": "Air Source Heat Pump", "Compressor_Start": "BO", "Temp_Sensor": "AI", ...}},
    ...
  ],
  "labor_estimate": [
    {{"System": "ASHP", "Equipment_Count": 3, "Points_Per_Equipment": 8, "Total_Points": 24, "Engineering": 12, "Programming": 24, ...}},
    ...
  ]
}}

CRITICAL: Start with {{ and end with }}. No markdown, no explanation."""
    
    return prompt
