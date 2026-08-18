"""
ground_truth.py

Compares this tool's extracted point list against an engineer-produced
point matrix, to answer the question coverage % cannot: not "how much of
the document was read" but "are the extracted points actually correct."

Built against a real point matrix (a 9-column table: System, Point
Description, Digital In/Out, Analog In/Out, Trend, Alarm, Notes) repeated
across pages with a shared header block. That is a common format for this
kind of document but not guaranteed universal - parse_point_matrix raises
clearly rather than silently returning an empty or garbled list if a given
PDF's table doesn't match the expected shape, since a comparison run against
a bad parse would produce a confidently wrong accuracy number, which is
worse than no number at all.
"""

import re
import difflib


# ============================================================================
# PARSING THE GROUND TRUTH PDF
# ============================================================================

def parse_point_matrix(pdf_path):
    """Extract a clean point list from an engineer-produced point matrix PDF.

    Expects a repeating table with columns roughly:
      System | Point Description | Digital-In | Digital-Out |
      Analog-In | Analog-Out | Trend | Alarm | Notes
    with a 4-row header block repeated on every page and the System column
    populated only where it changes (forward-filled here).

    Returns a list of dicts: system, point_description, io_type, notes, page.
    Raises ValueError if no table structure is found at all, rather than
    returning an empty list that would silently read as "0 ground truth
    points" downstream.
    """
    import fitz

    doc = fitz.open(pdf_path)
    points = []
    current_system = ""
    tables_found = 0

    for pno in range(len(doc)):
        page = doc[pno]
        for t in page.find_tables().tables:
            tables_found += 1
            df = t.to_pandas()
            if df.shape[1] < 8:
                # Not the expected column count - likely a different table
                # on the page (or a mis-detected region). Skip rather than
                # force-fit and produce garbage rows.
                continue

            # The first ~4 rows are the repeated header block (System /
            # Point Description / BMS Points / Hardware Points / Digital
            # /Analog / Input/Output). Detect it by checking whether row 0
            # contains header-like text rather than assuming a fixed count.
            data = df
            for skip in range(min(5, len(df))):
                row0 = [str(v).strip().lower() for v in df.iloc[skip].tolist()]
                if not any(h in " ".join(row0) for h in
                          ("point description", "system", "digital", "analog")):
                    data = df.iloc[skip:]
                    break

            for _, row in data.iterrows():
                vals = [("" if (v is None or str(v).lower() == "nan") else str(v).strip())
                       for v in row.tolist()]
                vals = (vals + [""] * 9)[:9]
                system, desc, di, do, ai, ao, trend, alarm, notes = vals

                if system:
                    current_system = re.sub(r"\s+", " ", system)
                if not desc or desc.lower() in ("point description", "nan"):
                    continue

                if di == "X":
                    io_type = "BI"
                elif do == "X":
                    io_type = "BO"
                elif ai == "X":
                    io_type = "AI"
                elif ao == "X":
                    io_type = "AO"
                else:
                    io_type = ""

                points.append({
                    "system": current_system,
                    "point_description": re.sub(r"\s+", " ", desc),
                    "io_type": io_type,
                    "notes": notes,
                    "page": pno + 1,
                })

    doc.close()

    if tables_found == 0:
        raise ValueError(
            "No table structure was found in this PDF. This parser expects "
            "a point-matrix table (System / Point Description / I-O columns "
            "/ Notes) repeated across pages - if this document uses a "
            "different layout, it needs a different parser, not this one."
        )
    if not points:
        raise ValueError(
            f"Found {tables_found} table(s) but extracted zero usable rows. "
            "The table's column layout may not match what this parser "
            "expects (System, Point Description, 4 I/O columns, Notes)."
        )
    return points


# ============================================================================
# MATCHING
# ============================================================================

def _normalize(text):
    """Lowercase, strip punctuation and extra whitespace for comparison."""
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _similarity(a, b):
    return difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def compare(extracted_points, ground_truth_points, threshold=0.6, confident_threshold=0.85):
    """Match extracted points against ground truth, one-to-one, greedily.

    Every (ground truth, extracted) pair is scored by name similarity, with
    a same-I/O-type match nudging the score up slightly as a tie-breaker.
    Pairs are assigned highest-score-first; once either side of a pair is
    used, it cannot be matched again - this prevents one strong extracted
    point (e.g. a generic "Status" point) from being credited as a match
    for several different ground-truth points.

    A single similarity threshold is not enough to trust blindly: two
    points that share vocabulary but describe different things (e.g. an
    "Elevator Pit Sump Alarm" and a "Elevator Sump Pump" point) can score
    above a permissive threshold without actually being the same point.
    Matches are therefore split into "confident" (>= confident_threshold)
    and "borderline" (between threshold and confident_threshold) tiers, and
    recall/precision are reported for both so a borderline-heavy result
    doesn't get quietly presented as equivalent to a confident one.

    Returns a dict with matched pairs (each tagged confident/borderline),
    missed ground-truth points (false negatives), extra extracted points
    (unmatched), and two sets of recall/precision numbers.
    """
    candidates = []
    for gi, gt in enumerate(ground_truth_points):
        for ei, ex in enumerate(extracted_points):
            score = _similarity(gt["point_description"], ex.get("Point_Name", ""))
            gt_io = gt.get("io_type", "")
            ex_io = next((k for k in ("AI", "BI", "AO", "BO")
                         if str(ex.get(k, "")).strip()), "")
            if gt_io and ex_io and gt_io == ex_io:
                score = min(1.0, score + 0.05)
            if score >= threshold:
                candidates.append((score, gi, ei))

    candidates.sort(key=lambda c: c[0], reverse=True)

    matched_gt, matched_ex = set(), set()
    matches = []
    for score, gi, ei in candidates:
        if gi in matched_gt or ei in matched_ex:
            continue
        matched_gt.add(gi)
        matched_ex.add(ei)
        matches.append({
            "ground_truth": ground_truth_points[gi],
            "extracted": extracted_points[ei],
            "similarity": round(score, 3),
            "tier": "confident" if score >= confident_threshold else "borderline",
        })

    missed = [gt for gi, gt in enumerate(ground_truth_points) if gi not in matched_gt]
    extra = [ex for ei, ex in enumerate(extracted_points) if ei not in matched_ex]

    confident = [m for m in matches if m["tier"] == "confident"]
    n_gt, n_ex = len(ground_truth_points), len(extracted_points)

    def rates(n_matched):
        return (round(n_matched / n_gt, 4) if n_gt else 0.0,
                round(n_matched / n_ex, 4) if n_ex else 0.0)

    recall_all, precision_all = rates(len(matches))
    recall_confident, precision_confident = rates(len(confident))

    return {
        "matches": matches,
        "missed": missed,
        "extra": extra,
        "n_ground_truth": n_gt,
        "n_extracted": n_ex,
        "n_matched": len(matches),
        "n_confident": len(confident),
        "n_borderline": len(matches) - len(confident),
        "recall_all": recall_all,
        "precision_all": precision_all,
        "recall_confident": recall_confident,
        "precision_confident": precision_confident,
    }


def summarize_by_system(ground_truth_points):
    """Ground-truth point counts per system, for a quick sanity check that
    the parse is sane before running a full comparison."""
    counts = {}
    for p in ground_truth_points:
        counts[p["system"]] = counts.get(p["system"], 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
