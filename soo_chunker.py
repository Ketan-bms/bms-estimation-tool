"""
soo_chunker.py

Splits an extracted SOO into section-aligned chunks for per-section analysis.

Why this exists
---------------
Asking one API call to enumerate every control point in a 45-page SOO produces
a response that runs past its length limit and gets cut off, losing the back
half of the document. Splitting the document along its own section boundaries
and running one call per section keeps every response comfortably inside limits
and gives each extracted point a verifiable source.

This module deliberately contains no API calls and no Streamlit imports, so it
can be tested directly against a real SOO.
"""

import re

# A section number sitting alone on a line: "1.7", "3.10"
_SECTION_NUM = re.compile(r'^\s*(\d+\.\d+)\s*$')

# "PART 1 - GENERAL"
_PART = re.compile(r'^\s*(PART\s+\d+\b.*)$', re.IGNORECASE)

# Page markers inserted during PDF extraction
_PAGE_MARKER = re.compile(r'^--- PAGE (\d+) ---\s*$')

# Sections that are contractual boilerplate rather than control sequences.
# Kept as data, not hardcoded logic, so it can be adjusted per specification.
BOILERPLATE_TITLES = (
    "RELATED DOCUMENTS",
    "SUMMARY",
    "DEFINITIONS",
    "SUBMITTALS",
    "QUALITY ASSURANCE",
    "REFERENCES",
    "WARRANTY",
)


class Section:
    """One section of the SOO, with the pages it came from."""

    __slots__ = ("number", "title", "text", "start_page", "end_page", "is_sequence")

    def __init__(self, number, title, text, start_page, end_page, is_sequence):
        self.number = number
        self.title = title
        self.text = text
        self.start_page = start_page
        self.end_page = end_page
        self.is_sequence = is_sequence

    @property
    def label(self):
        return f"{self.number} {self.title}".strip() if self.number else self.title

    @property
    def page_range(self):
        if self.start_page == self.end_page:
            return str(self.start_page)
        return f"{self.start_page}-{self.end_page}"

    def __repr__(self):
        return (f"<Section {self.label!r} pages {self.page_range} "
                f"{len(self.text)} chars seq={self.is_sequence}>")


def _looks_like_boilerplate(number, title):
    """General/administrative sections carry no control points."""
    upper = (title or "").upper()
    if any(key in upper for key in BOILERPLATE_TITLES):
        return True
    # "GENERAL" only counts as boilerplate when it is the whole title,
    # so that "GENERAL EXHAUST" is not discarded.
    if upper.strip() == "GENERAL":
        return True
    return False


def parse_sections(text):
    """Split extracted SOO text into Section objects.

    `text` is expected to contain "--- PAGE n ---" markers, as produced by the
    PDF extraction step. If no headings are found, the whole document is
    returned as a single section so callers always get usable output.
    """
    lines = text.split("\n")

    # Walk once, tracking the current page and collecting heading positions.
    page_at_line = []
    current_page = 1
    for line in lines:
        m = _PAGE_MARKER.match(line.strip())
        if m:
            current_page = int(m.group(1))
        page_at_line.append(current_page)

    headings = []  # (line_index, number, title)
    for i, line in enumerate(lines):
        stripped = line.strip()

        m = _PART.match(stripped)
        if m:
            headings.append((i, "", m.group(1).strip()))
            continue

        m = _SECTION_NUM.match(line)
        if m:
            # The title normally sits on the next non-empty line.
            title = ""
            for j in range(i + 1, min(i + 4, len(lines))):
                candidate = lines[j].strip()
                if candidate:
                    title = candidate
                    break
            headings.append((i, m.group(1), title))

    if not headings:
        return [Section("", "Full document", text, 1,
                        page_at_line[-1] if page_at_line else 1, True)]

    sections = []
    for idx, (line_no, number, title) in enumerate(headings):
        end_line = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
        body = "\n".join(lines[line_no:end_line]).strip()
        if not body:
            continue
        sections.append(Section(
            number=number,
            title=title,
            text=body,
            start_page=page_at_line[line_no],
            end_page=page_at_line[min(end_line, len(page_at_line)) - 1],
            is_sequence=not _looks_like_boilerplate(number, title),
        ))
    return sections


def _split_oversized(section, max_chars):
    """Break one very long section into paragraph-aligned pieces.

    Splitting mid-sentence would strand a point description away from its
    equipment tag, so paragraph boundaries are used and each piece keeps the
    original section heading for context.
    """
    paragraphs = section.text.split("\n\n")
    pieces, buffer = [], ""

    for para in paragraphs:
        if buffer and len(buffer) + len(para) + 2 > max_chars:
            pieces.append(buffer)
            buffer = para
        else:
            buffer = f"{buffer}\n\n{para}" if buffer else para
    if buffer:
        pieces.append(buffer)

    out = []
    for n, piece in enumerate(pieces, 1):
        header = f"{section.label} (part {n} of {len(pieces)})\n\n"
        out.append(Section(
            number=section.number,
            title=f"{section.title} (part {n}/{len(pieces)})",
            text=header + piece,
            start_page=section.start_page,
            end_page=section.end_page,
            is_sequence=section.is_sequence,
        ))
    return out


def build_chunks(text, max_chars=14000, min_chars=300, sequences_only=True):
    """Return the list of Sections to run extraction against.

    min_chars drops heading stubs that contain no sequence text.

    max_chars bounds each chunk so no single response has to enumerate more
    points than it can hold. Sections below the bound are never merged with
    their neighbours: keeping one section per chunk means every extracted
    point maps to exactly one identifiable source.

    sequences_only drops administrative sections, which contain no points and
    would otherwise waste a call each.
    """
    sections = parse_sections(text)

    # Drop stubs such as a bare "PART 2 - PRODUCTS" line. They carry no
    # sequence content and would each cost an API call to confirm as empty.
    sections = [s for s in sections if len(s.text) >= min_chars]

    if sequences_only:
        candidates = [s for s in sections if s.is_sequence]
        # Never return nothing: if the heuristic filtered everything out,
        # fall back to the full set rather than silently analysing zero pages.
        if not candidates:
            candidates = sections
    else:
        candidates = sections

    chunks = []
    for section in candidates:
        if len(section.text) > max_chars:
            chunks.extend(_split_oversized(section, max_chars))
        else:
            chunks.append(section)
    return chunks


def coverage_report(text, chunks):
    """Summarise how much of the document will actually be analysed.

    Silent under-coverage is the failure mode this whole module exists to
    prevent, so the numbers are made available to the caller rather than
    assumed correct.
    """
    total = len(text)
    covered = sum(len(c.text) for c in chunks)
    return {
        "total_chars": total,
        "analysed_chars": covered,
        "coverage_pct": round(100.0 * covered / total, 1) if total else 0.0,
        "chunk_count": len(chunks),
        "largest_chunk": max((len(c.text) for c in chunks), default=0),
    }
