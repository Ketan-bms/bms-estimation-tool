"""
pdf_takeoff.py
──────────────
Pure PyMuPDF takeoff engine — no Claude API needed.

How it works:
  1. Open drawing PDF with PyMuPDF
  2. Scan every page for BMS device tags using regex on text layer
  3. Identify schedule pages (dense tables with equipment headers)
  4. For each unique tag found: record page, floor, system type
  5. Cross-check against SOO tag set → assign status
  6. Return structured equipment list + discrepancies

No token limits. No API cost. Works on any CAD-exported PDF.
Takes ~5-10 seconds for a 15MB drawing set.
"""

import re
import json
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Optional
import fitz  # PyMuPDF


# ── Tag detection regex ───────────────────────────────────────────────────────
# Matches BMS device tags like FCU-SC-1, AHU-1M-2, DOAS-12-1, EUH-35-2 etc.
TAG_RE = re.compile(
    r'\b((?:ASHP|DOAS|MUA|MAU|ESP|AHU|ERV|FCU|ACU|ACCU|EUH|UH|FTR|HWC|'
    r'PFHX|PCHWP|SCHWP|PHWP|SHWP|FPP|BT|GFU|FOP|'
    r'PFSP|SPF|HPF|GX|EF|HF|TF|VAV|AC-C|ACCU)'
    r'[-][A-Z0-9]+[-][A-Z0-9]+(?:[-][A-Z0-9]+)?'   # e.g. FCU-SC-1, DOAS-12-1
    r'|(?:ASHP|ESP|AHU|ERV|MAU|MUA)-\d+[A-Z]?[-]\d+'  # e.g. AHU-1M-1
    r'|(?:ASHP)-\d'                                   # e.g. ASHP-1
    r')\b',
    re.IGNORECASE
)

# Schedule page detection keywords
SCHEDULE_KEYWORDS = [
    "SCHEDULE", "DESIGNATION", "CFM", "MBH", "GPM", "MOTOR HP",
    "MANUFACTURER", "MODEL NUMBER", "ELECTRICAL", "V/∅/Hz",
    "AREA SERVED", "CAPACITY", "EWT", "LWT", "ROWS", "FPI", "VOLTAGE"
]

# Floor mapping from tag suffix
FLOOR_MAP = {
    "SC": "Subcellar", "C": "Cellar",
    "1M": "1st/Mezzanine", "1": "1st Floor",
    "2M": "2nd Floor Mezz", "2": "2nd Floor",
    "12": "12th Floor", "33": "33rd Floor",
    "34": "34th Floor", "35": "35th Floor",
    "36": "36th Floor", "R": "Roof",
}

# System classification from tag prefix
SYSTEM_MAP = {
    "FCU":   ("Fan Coil Unit",              "Terminal / FCU",          "DDC"),
    "AHU":   ("Air Handling Unit",           "Air Handling / AHU",      "BACnet"),
    "DOAS":  ("DOAS w/ Enthalpy Wheel",      "Air Handling / DOAS",     "BACnet"),
    "MUA":   ("Make Up Air Unit",            "Air Handling / MUA",      "BACnet"),
    "MAU":   ("Make Up Air Unit",            "Air Handling / MUA",      "BACnet"),
    "ERV":   ("Energy Recovery Ventilator",  "Air Handling / ERV",      "BACnet"),
    "ESP":   ("Electrostatic Precipitator",  "Air Quality / ESP",       "BACnet"),
    "ASHP":  ("Modular Air Source Heat Pump","Primary Plant / Heat Pump","BACnet"),
    "PCHWP": ("Primary CHW Pump",            "Hydronic / Pump",         "BMS VFD"),
    "SCHWP": ("Secondary CHW Pump",          "Hydronic / Pump",         "BMS VFD"),
    "PHWP":  ("Primary HW Pump",             "Hydronic / Pump",         "BMS VFD"),
    "SHWP":  ("Secondary HW Pump",           "Hydronic / Pump",         "BMS VFD"),
    "FPP":   ("Freeze Protection Pump",      "Hydronic / Pump",         "BMS"),
    "PFHX":  ("Plate & Frame Heat Exchanger","Primary Plant / HX",      "BMS"),
    "BT":    ("Buffer Tank",                 "Hydronic / Tank",         "BMS"),
    "GFU":   ("Glycol Make-Up Unit",         "Hydronic / Ancillary",    "BMS"),
    "FOP":   ("Fuel Oil Pump",               "Ancillary / FOP",         "BMS"),
    "EUH":   ("Electric Unit Heater",        "Terminal / EUH",          "None"),
    "UH":    ("Hot Water Unit Heater",        "Terminal / UH",           "None"),
    "FTR":   ("Fin Tube Radiation",          "Terminal / FTR",          "BMS"),
    "HWC":   ("Hot Water Coil",              "Hydronic / HW Coil",      "BMS"),
    "VAV":   ("VAV Terminal Box",            "Terminal / VAV",          "DDC"),
    "ACU":   ("Split AC Unit (Indoor)",      "Terminal / Split AC",     "BACnet"),
    "ACCU":  ("Split AC Unit (Outdoor)",     "Terminal / Split AC",     "BACnet"),
    "AC":    ("Split AC Unit",               "Terminal / Split AC",     "BACnet"),
    "PFSP":  ("Post Fire Smoke Purge Fan",   "Life Safety / Fan",       "BACnet"),
    "SPF":   ("Stair Pressurization Fan",    "Life Safety / Fan",       "BACnet"),
    "HPF":   ("Hoistway Pressurization Fan", "Life Safety / Fan",       "BACnet"),
    "GX":    ("General Exhaust Fan",         "Life Safety / Fan",       "BACnet"),
    "EF":    ("Exhaust Fan",                 "Exhaust / Fan",           "BMS"),
    "HF":    ("Hoistway Ventilation Fan",    "Exhaust / Fan",           "BMS"),
    "TF":    ("LV Closet Ventilation Fan",   "Exhaust / Fan",           "None"),
}

# SOO confirmed tags — extracted from the project SOO document
# (23 09 93 — Sequence of Operations, 255 West 34th Street Hotel)
SOO_CONFIRMED_TAGS = {
    "ASHP-1","ASHP-2","ASHP-3",
    "DOAS-1M-1","DOAS-12-1","DOAS-12-2",
    "MUA-1M-1","MAU-1M-1","AHU-1M-1","AHU-1M-2",
    "ERV-2M-1","ERV-35-1","ESP-12-1",
    "FCU-SC-1","FCU-SC-2","FCU-SC-3","FCU-SC-4",
    "FCU-SC-5","FCU-SC-6","FCU-SC-7","FCU-SC-8",
    "FCU-C-1","FCU-C-2","FCU-C-3","FCU-C-4","FCU-C-5","FCU-C-6",
    "FCU-12-1","FCU-2-1","FCU-2M-1","FCU-2M-2","FCU-2M-3",
    "FCU-33-1","FCU-33-2","FCU-33-3","FCU-33-4",
    "FCU-A","FCU-B",
    "ACU-35-1","ACU-35-2","ACU-35-3","ACU-36-1",
    "ACCU-35-1","ACCU-35-2","ACCU-36-1","AC-C-1",
    "HWC-12-1","HWC-12-2","HWC-34-1","FTR-A",
    "GX-35-1","GX-12-1","GX-12-2","TF-1",
    "EF-C-1","EF-1M-1","HF-2M-1",
    "PCHWP-34-1","PCHWP-34-2","PCHWP-34-3",
    "SCHWP-34-1","SCHWP-34-2","SCHWP-34-3",
    "PHWP-34-1","PHWP-34-2","PHWP-34-3",
    "SHWP-34-1","SHWP-34-2","SHWP-34-3",
    "FPP-1M-1","FPP-1M-2","FPP-12-1","FPP-12-2",
    "FPP-12-3","FPP-12-4","FPP-34-1",
    "PFHX-34-1","PFHX-34-2","PFHX-34-3",
    "BT-34-1","BT-34-2","BT-34-3",
    "GFU-34-1","GFU-34-2","FOP-SC-1","FOP-SC-2",
    "PFSP-1M-1","PFSP-2M-1","PFSP-12-1",
    "SPF-35-1","SPF-36-1","HPF-35-1",
}

# Confirmed NOT in SOO — no sequence anywhere in 59 pages
SOO_MISSING_TAGS = {
    "EUH-SC-1","EUH-SC-2","EUH-1-1","EUH-35-1","EUH-35-2",
    "UH-SC-1","UH-SC-2","UH-C-1",
    "UH-12-1","UH-12-2","UH-12-3","UH-34-1",
}


def _floor_from_tag(tag: str) -> str:
    """Extract floor label from tag suffix convention."""
    tag_upper = tag.upper()
    # e.g. FCU-SC-1 -> SC, AHU-1M-2 -> 1M, ASHP-1 -> Roof
    if tag_upper.startswith("ASHP"):
        return "Roof"
    parts = tag_upper.split("-")
    if len(parts) >= 2:
        key = parts[1]
        return FLOOR_MAP.get(key, key)
    return "Unknown"


def _system_from_tag(tag: str) -> tuple:
    """Return (system_name, classification, bms_interface) from tag prefix."""
    tag_upper = tag.upper()
    for prefix, info in SYSTEM_MAP.items():
        if tag_upper.startswith(prefix):
            return info
    return ("Unknown", "Unknown", "Unknown")


def _is_schedule_page(page_text: str) -> bool:
    """Detect if a page is a schedule sheet."""
    text_upper = page_text.upper()
    hits = sum(1 for kw in SCHEDULE_KEYWORDS if kw.upper() in text_upper)
    return hits >= 4


def run_pdf_takeoff(pdf_bytes: bytes,
                    soo_confirmed: set = None,
                    soo_missing: set = None) -> dict:
    """
    Main entry point. Reads PDF bytes, extracts all BMS tags,
    cross-checks against SOO, returns equipment list + discrepancies.

    Args:
        pdf_bytes:     Raw PDF bytes from the uploaded drawing set
        soo_confirmed: Override the built-in SOO confirmed set (optional)
        soo_missing:   Override the built-in SOO missing set (optional)

    Returns:
        {
          "equipment": [...],       # list of device dicts
          "discrepancies": [...],   # list of amber/red device dicts
          "stats": {...},           # summary counts
          "schedule_pages": [...],  # list of page numbers identified as schedules
        }
    """
    confirmed = {t.upper() for t in (soo_confirmed or SOO_CONFIRMED_TAGS)}
    missing   = {t.upper() for t in (soo_missing   or SOO_MISSING_TAGS)}

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)

    # Pass 1: identify schedule pages and extract all tags with locations
    schedule_pages = set()
    tag_data: dict[str, dict] = {}  # tag_upper -> {pages, first_page, on_schedule}

    for page_idx in range(total_pages):
        page = doc[page_idx]
        text = page.get_text()
        is_schedule = _is_schedule_page(text)
        if is_schedule:
            schedule_pages.add(page_idx)

        # Find all tag matches on this page
        found = set(m.upper() for m in TAG_RE.findall(text))

        for tag in found:
            if tag not in tag_data:
                tag_data[tag] = {
                    "pages": [],
                    "first_page": page_idx + 1,
                    "found_on_schedule": is_schedule,
                    "found_on_floorplan": not is_schedule,
                }
            tag_data[tag]["pages"].append(page_idx + 1)
            if not is_schedule:
                tag_data[tag]["found_on_floorplan"] = True

    doc.close()

    # Pass 2: build equipment list with status
    equipment = []
    discrepancies = []

    for tag, data in sorted(tag_data.items()):
        system, classification, bms = _system_from_tag(tag)
        floor = _floor_from_tag(tag)

        # Determine SOO status
        in_soo  = tag in confirmed
        is_disc = tag in missing

        if is_disc:
            soo_confirmed_flag = False
            disc_flag          = True
            action = (
                "Integral/standalone thermostat — no BMS control sequence in SOO. "
                "Confirm with engineer: is BMS monitoring point required?"
            )
        elif in_soo:
            soo_confirmed_flag = True
            disc_flag          = False
            action             = ""
        else:
            # Found on drawing, not in our known sets — needs review
            soo_confirmed_flag = None
            disc_flag          = None
            action             = "Verify BMS scope — not in known SOO tag list."

        device = {
            "tag":                  tag,
            "qty":                  1,
            "floor":                floor,
            "system":               system,
            "classification":       classification,
            "bms_interface_default": bms,
            "soo_confirmed":        soo_confirmed_flag,
            "discrepancy_flag":     disc_flag,
            "action":               action,
            "found_pages":          sorted(set(data["pages"]))[:6],
            "found_on_floorplan":   data["found_on_floorplan"],
        }
        equipment.append(device)

        if disc_flag is True:
            discrepancies.append({
                "tag":    tag,
                "system": system,
                "floor":  floor,
                "action": action,
            })

    stats = {
        "total_pages":      total_pages,
        "schedule_pages":   len(schedule_pages),
        "total_tags":       len(equipment),
        "soo_confirmed":    sum(1 for e in equipment if e["soo_confirmed"] is True),
        "discrepancies":    len(discrepancies),
        "needs_review":     sum(1 for e in equipment if e["soo_confirmed"] is None),
    }

    return {
        "equipment":      equipment,
        "discrepancies":  discrepancies,
        "stats":          stats,
        "schedule_pages": sorted(schedule_pages),
    }


def takeoff_to_session_format(result: dict) -> dict:
    """
    Convert run_pdf_takeoff output to the format expected by
    p["takeoff"] in app.py session state.
    """
    return {
        "equipment":    result["equipment"],
        "discrepancies": result["discrepancies"],
        "status":       "issues" if result["discrepancies"] else "done",
        "stats":        result["stats"],
    }
