"""
project_store.py

Keeps analysed projects available across page refreshes, and lets a project
be exported to a file so it survives beyond the life of the server process.

A note on durability
--------------------
Streamlit Community Cloud runs the app in a container that is recycled when
the app sleeps, is redeployed, or is restarted. Anything held in memory goes
with it. The in-memory registry below therefore covers working within a
session and across page refreshes - it is not a database, and it is not a
backup.

Export is the durable path. A project file is plain JSON containing the full
analysis, so it can be committed, emailed, or re-imported on another machine.
The UI treats export as the way to keep a project, not as an afterthought.
"""

import json
import re
from datetime import datetime


def _slug(name):
    """Filesystem- and key-safe form of a project name."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip())
    return cleaned.strip("_") or "project"


def make_record(project_name, source_filename, analysis_results):
    """Wrap an analysis in a portable record with its own metadata."""
    metadata = analysis_results.get("metadata", {}) or {}
    return {
        "schema": 1,
        "project_name": project_name,
        "source_file": source_filename,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": {
            "points": metadata.get("total_points_extracted", 0),
            "io_count": metadata.get("total_i_o_count", 0),
            "pages": metadata.get("soo_pages", 0),
            "coverage_pct": (metadata.get("coverage", {}) or {}).get("coverage_pct"),
            "sections_failed": len(metadata.get("sections_failed", []) or []),
        },
        "analysis": analysis_results,
    }


def to_json(record):
    """Serialise a project record for download."""
    return json.dumps(record, indent=2, default=str)


def from_json(raw):
    """Parse an uploaded project file, rejecting anything unrecognisable.

    Import is a path by which malformed or unrelated files reach the rest of
    the app, so the shape is checked here rather than trusted.
    """
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Not a valid project file: {e}") from e

    if not isinstance(record, dict) or "analysis" not in record:
        raise ValueError(
            "This file does not look like a project export. Expected a JSON "
            "object containing an 'analysis' key."
        )

    analysis = record.get("analysis")
    if not isinstance(analysis, dict) or "point_list" not in analysis:
        raise ValueError("Project file is missing its point list.")

    record.setdefault("project_name", "Imported project")
    record.setdefault("source_file", "")
    record.setdefault("saved_at", "")
    record.setdefault("summary", {})
    return record


def export_filename(project_name):
    return f"{_slug(project_name)}_project.json"


class ProjectRegistry:
    """In-memory set of projects, keyed by name.

    Held via st.cache_resource in the app so it survives page refreshes for
    as long as the server process lives.
    """

    def __init__(self):
        self._projects = {}

    def save(self, record):
        name = record.get("project_name") or "Untitled"
        self._projects[name] = record
        return name

    def get(self, name):
        return self._projects.get(name)

    def delete(self, name):
        self._projects.pop(name, None)

    def names(self):
        """Most recently saved first."""
        return sorted(
            self._projects,
            key=lambda n: self._projects[n].get("saved_at", ""),
            reverse=True,
        )

    def rows(self):
        """Table-ready summary of every stored project."""
        out = []
        for name in self.names():
            record = self._projects[name]
            summary = record.get("summary", {}) or {}
            out.append({
                "Project": name,
                "Source": record.get("source_file", ""),
                "Saved": record.get("saved_at", ""),
                "Points": summary.get("points", ""),
                "I/O": summary.get("io_count", ""),
                "Pages": summary.get("pages", ""),
                "Coverage": (f"{summary['coverage_pct']}%"
                             if summary.get("coverage_pct") is not None else ""),
                "Failed sections": summary.get("sections_failed", 0),
            })
        return out

    def __len__(self):
        return len(self._projects)
