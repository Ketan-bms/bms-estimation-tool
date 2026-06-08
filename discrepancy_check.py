"""
discrepancy_check.py
────────────────────
BMS Estimation Tool — Discrepancy Check Engine
West 34th Street Hotel

Finds gaps between three source-of-truth layers:
  1. Schedule ground truth  (schedule_ground_truth.json)
  2. SOO references         (soo_refs.json)
  3. Drawing takeoff        (markup_extractor output / takeoff JSON)

Produces a unified DiscrepancyReport used by:
  - Streamlit UI     (app.py)
  - CLI batch mode   (python discrepancy_check.py --report)
  - API endpoint     (FastAPI wrapper, optional)

Usage:
    python discrepancy_check.py --schedule output/schedule_ground_truth.json
                                --soo      output/soo_refs.json
                                --takeoff  output/takeoff_results.json   [optional]
                                --out      output/discrepancy_report.json
"""

import json
import re
import argparse
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


# ─── DATA CLASSES ────────────────────────────────────────────────────────────

@dataclass
class Discrepancy:
    tag: str
    system: str
    classification: str
    floor: str
    issue: str                        # short machine key
    severity: str                     # HIGH / MEDIUM / LOW
    description: str                  # human sentence
    action: str                       # what the estimator should do
    source_schedule: bool = False
    source_soo: bool = False
    source_takeoff: bool = False
    resolution: Optional[str] = None  # filled by reviewer


@dataclass
class DiscrepancyReport:
    project: str
    schedule_file: str
    soo_file: str
    takeoff_file: Optional[str]
    generated: str
    summary: dict = field(default_factory=dict)
    discrepancies: list = field(default_factory=list)
    confirmed: list = field(default_factory=list)
    needs_review: list = field(default_factory=list)
    stats_by_classification: dict = field(default_factory=dict)
    stats_by_floor: dict = field(default_factory=dict)


# ─── LOADERS ─────────────────────────────────────────────────────────────────

def load_schedule(path: str) -> dict:
    with open(path) as f:
        data = json.load(f)
    equip = data.get("equipment", [])
    by_tag = {e["tag"]: e for e in equip}
    return {"raw": data, "equipment": equip, "by_tag": by_tag,
            "tags": set(by_tag.keys())}


def load_soo(path: str) -> dict:
    """
    soo_refs.json shape (flexible — handles two formats):
      A) {"systems": {"FCU": {"tags": [...], "sequence": "..."}}}
      B) {"tags": [...], "entries": [...]}
    """
    with open(path) as f:
        data = json.load(f)

    tags: set[str] = set()
    system_map: dict[str, list[str]] = {}

    if "systems" in data:
        for sys_name, sys_data in data["systems"].items():
            t = sys_data.get("tags", [])
            tags.update(t)
            system_map[sys_name] = t
    if "tags" in data:
        tags.update(data["tags"])
    if "entries" in data:
        for e in data["entries"]:
            t = e.get("tag") or e.get("tags", [])
            if isinstance(t, str):
                tags.add(t)
            else:
                tags.update(t)

    return {"raw": data, "tags": tags, "system_map": system_map}


def load_takeoff(path: Optional[str]) -> Optional[dict]:
    if not path or not Path(path).exists():
        return None
    with open(path) as f:
        data = json.load(f)
    # Support both schedule_ground_truth format and takeoff_results format
    tags: set[str] = set()
    if "equipment" in data:
        tags = {e["tag"] for e in data["equipment"]}
    elif "takeoff" in data:
        for row in data["takeoff"]:
            t = row.get("Tag") or row.get("tag")
            if t:
                tags.add(str(t).strip())
    return {"raw": data, "tags": tags}


# ─── CROSS-CHECK ENGINE ──────────────────────────────────────────────────────

# Severity rules — order matters, first match wins
SEVERITY_RULES = [
    # EUH / UH: real money scope questions
    (lambda tag, cls: "EUH" in tag or (tag.startswith("UH-") and "Unit Heater" in cls),
     "HIGH",
     "in_schedule_not_in_soo",
     "Device is scheduled with integral/standalone thermostat and has no SOO sequence. "
     "Confirm whether BMS monitoring point (alarm, status, or sensor) is required.",
     "Clarify BMS scope with engineer. If monitoring required, add DI status point and "
     "program alarm. If standalone only, document as excluded."),

    # Life Safety — in schedule, not confirmed in SOO
    (lambda tag, cls: "Life Safety" in cls,
     "HIGH",
     "life_safety_no_soo",
     "Life safety fan appears in schedule without SOO sequence confirmation.",
     "Verify fire alarm interlock sequence with FP engineer. Confirm BACnet integration "
     "points and override logic."),

    # Primary plant (ASHP, HX, pumps) without SOO
    (lambda tag, cls: "Primary Plant" in cls or "Hydronic / Pump" in cls,
     "MEDIUM",
     "primary_plant_no_soo",
     "Primary plant device in schedule has no confirmed SOO sequence.",
     "Confirm staging/lead-lag logic, setpoints, and VFD control sequence with engineer."),

    # Anything else in schedule not in SOO
    (lambda tag, cls: True,
     "LOW",
     "in_schedule_not_in_soo",
     "Device appears in schedule but was not found in SOO.",
     "Verify device requires BMS integration. If so, request SOO from engineer."),
]

# SOO tag → schedule: usually means a renamed or missing tag
SOO_NOT_SCHEDULE_RULES = [
    (lambda tag: True,
     "LOW",
     "in_soo_not_in_schedule",
     "Tag referenced in SOO but not found in schedule.",
     "Verify tag was not renamed or is on a separate drawing set."),
]


def classify_discrepancy(tag: str, cls: str, issue_type: str) -> tuple[str, str, str]:
    """Returns (severity, issue_key, action)."""
    if issue_type == "in_soo_not_in_schedule":
        return "LOW", "in_soo_not_in_schedule", \
               "Verify tag was not renamed or lives on a separate drawing set."
    for predicate, sev, key, _desc, action in SEVERITY_RULES:
        if predicate(tag, cls):
            return sev, key, action
    return "LOW", "unknown", "Review manually."


def run(schedule_path: str,
        soo_path: str,
        takeoff_path: Optional[str] = None) -> DiscrepancyReport:

    from datetime import datetime

    sch = load_schedule(schedule_path)
    soo = load_soo(soo_path)
    tkf = load_takeoff(takeoff_path)

    sch_tags = sch["tags"]
    soo_tags = soo["tags"]
    tkf_tags = tkf["tags"] if tkf else set()

    # ── Set arithmetic ───────────────────────────────────────────────────────
    in_sch_not_soo = sorted(sch_tags - soo_tags)
    in_soo_not_sch = sorted(soo_tags - sch_tags)
    confirmed_both = sorted(sch_tags & soo_tags)

    # Also check takeoff vs schedule (if available)
    in_tkf_not_sch = sorted(tkf_tags - sch_tags) if tkf_tags else []
    in_sch_not_tkf = sorted(sch_tags - tkf_tags) if tkf_tags else []

    # ── Build discrepancy list ───────────────────────────────────────────────
    discrepancies: list[Discrepancy] = []

    for tag in in_sch_not_soo:
        rec = sch["by_tag"].get(tag, {})
        cls = rec.get("classification", "Unknown")
        sys_name = rec.get("system", "Unknown")
        floor = rec.get("floor", "Unknown")
        sev, key, action = classify_discrepancy(tag, cls, "in_schedule_not_in_soo")

        # Find description from severity rules
        desc = next(
            (d for pred, _, k, d, _ in SEVERITY_RULES if pred(tag, cls)), ""
        )
        discrepancies.append(Discrepancy(
            tag=tag, system=sys_name, classification=cls,
            floor=floor, issue=key, severity=sev,
            description=desc, action=action,
            source_schedule=True, source_soo=False,
        ))

    for tag in in_soo_not_sch:
        discrepancies.append(Discrepancy(
            tag=tag, system="Unknown (SOO only)", classification="Unknown",
            floor="Unknown", issue="in_soo_not_in_schedule", severity="LOW",
            description="Tag in SOO but not found in schedule.",
            action="Verify tag was not renamed or is on a separate drawing set.",
            source_schedule=False, source_soo=True,
        ))

    for tag in in_tkf_not_sch:
        discrepancies.append(Discrepancy(
            tag=tag, system="Unknown (takeoff only)", classification="Unknown",
            floor="Unknown", issue="in_takeoff_not_in_schedule", severity="LOW",
            description="Tag found in drawing takeoff but not in schedule.",
            action="Check if this is a new tag or OCR artifact. Cross-reference drawing.",
            source_schedule=False, source_soo=False, source_takeoff=True,
        ))

    # ── Stats by classification ──────────────────────────────────────────────
    stats_cls: dict[str, dict] = {}
    for e in sch["equipment"]:
        cls = e.get("classification", "Unknown")
        if cls not in stats_cls:
            stats_cls[cls] = {"total": 0, "confirmed": 0, "discrepancy": 0, "review": 0}
        stats_cls[cls]["total"] += 1
        if e.get("soo_confirmed") is True:
            stats_cls[cls]["confirmed"] += 1
        elif e.get("discrepancy_flag") is True:
            stats_cls[cls]["discrepancy"] += 1
        else:
            stats_cls[cls]["review"] += 1

    stats_floor: dict[str, dict] = {}
    for e in sch["equipment"]:
        fl = e.get("floor", "Unknown")
        if fl not in stats_floor:
            stats_floor[fl] = {"total": 0, "discrepancy": 0}
        stats_floor[fl]["total"] += 1
        if e.get("discrepancy_flag") is True:
            stats_floor[fl]["discrepancy"] += 1

    # ── Needs review list ─────────────────────────────────────────────────────
    needs_review = [
        e for e in sch["equipment"]
        if e.get("soo_confirmed") is None and not e.get("discrepancy_flag")
    ]

    # ── Build report ──────────────────────────────────────────────────────────
    report = DiscrepancyReport(
        project=sch["raw"].get("project", "Unknown"),
        schedule_file=schedule_path,
        soo_file=soo_path,
        takeoff_file=takeoff_path,
        generated=datetime.now().isoformat(),
        summary={
            "schedule_tags": len(sch_tags),
            "soo_tags": len(soo_tags),
            "confirmed_both": len(confirmed_both),
            "in_schedule_not_soo": len(in_sch_not_soo),
            "in_soo_not_schedule": len(in_soo_not_sch),
            "needs_review": len(needs_review),
            "high_severity": sum(1 for d in discrepancies if d.severity == "HIGH"),
            "medium_severity": sum(1 for d in discrepancies if d.severity == "MEDIUM"),
            "low_severity": sum(1 for d in discrepancies if d.severity == "LOW"),
        },
        discrepancies=[asdict(d) for d in discrepancies],
        confirmed=confirmed_both,
        needs_review=[e.get("tag") for e in needs_review],
        stats_by_classification=stats_cls,
        stats_by_floor=stats_floor,
    )
    return report


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="BMS Discrepancy Check Engine")
    parser.add_argument("--schedule", required=True)
    parser.add_argument("--soo",      required=True)
    parser.add_argument("--takeoff",  default=None)
    parser.add_argument("--out",      default="output/discrepancy_report.json")
    parser.add_argument("--report",   action="store_true", help="Print human-readable summary")
    args = parser.parse_args()

    report = run(args.schedule, args.soo, args.takeoff)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(asdict(report), f, indent=2)

    if args.report:
        s = report.summary
        print(f"\n{'═'*56}")
        print(f"  BMS DISCREPANCY REPORT — {report.project}")
        print(f"{'═'*56}")
        print(f"  Schedule tags:      {s['schedule_tags']}")
        print(f"  SOO tags:           {s['soo_tags']}")
        print(f"  Confirmed (both):   {s['confirmed_both']}")
        print(f"  ─────────────────────────────────────────")
        print(f"  In schedule/not SOO:{s['in_schedule_not_soo']}  "
              f"(HIGH:{s['high_severity']} MED:{s['medium_severity']} LOW:{s['low_severity']})")
        print(f"  In SOO/not schedule:{s['in_soo_not_schedule']}")
        print(f"  Needs review:       {s['needs_review']}")
        print(f"{'─'*56}")
        high = [d for d in report.discrepancies if d["severity"] == "HIGH"]
        if high:
            print(f"\n  ⚠  HIGH SEVERITY ({len(high)}):")
            for d in high:
                print(f"     {d['tag']:20s}  {d['system']}")
                print(f"     {'':20s}  → {d['action']}")
        print(f"\n  Full report: {args.out}\n")

    print(f"[OK] Discrepancy report written to {args.out}")
    print(f"     {report.summary['in_schedule_not_soo']} discrepancies "
          f"| {report.summary['high_severity']} HIGH severity")


if __name__ == "__main__":
    main()
