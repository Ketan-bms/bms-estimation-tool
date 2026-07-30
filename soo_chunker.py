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

# A subsection letter alone on a line: "A.", "B."
# Specifications differ in how deep the equipment level sits. Some put each
# system under its own N.N heading; others put every system under a single
# heading such as "3.2 SEQUENCE OF OPERATION" and separate them by letter.
# Detecting both means one chunker handles both layouts.
# Single or double letter: specifications that run past Z continue with
# AA, BB, CC. Missing those loses every system past the twenty-sixth.
_LETTER_HEADING = re.compile(r'^\s*([A-Z]{1,2})\.\s*$')

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

    __slots__ = ("number", "title", "text", "start_page", "end_page",
                 "is_sequence", "line_start", "page_map")

    def __init__(self, number, title, text, start_page, end_page, is_sequence,
                 line_start=0, page_map=None):
        self.number = number
        self.title = title
        self.text = text
        self.start_page = start_page
        self.end_page = end_page
        self.is_sequence = is_sequence
        # Absolute line index in the source document, plus the document-wide
        # line->page map. Without these a subsection inherits its parent's
        # page span, which for a 100-page section is useless as provenance.
        self.line_start = line_start
        self.page_map = page_map or []

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
                        page_at_line[-1] if page_at_line else 1, True,
                        line_start=0, page_map=page_at_line)]

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
            line_start=line_no,
            page_map=page_at_line,
        ))
    return sections


def find_subsections(text):
    """Locate lettered subsection headings and their titles.

    Returns (line_index, letter, title). A heading is a bare "A." followed by
    a short line that does not read as a sentence. The title may be Title
    Case or upper case, so casing is not used as the test; length and the
    absence of terminal punctuation are more reliable across specifications.
    """
    lines = text.split("\n")
    out = []
    for i, line in enumerate(lines):
        m = _LETTER_HEADING.match(line)
        if not m:
            continue
        title = ""
        for j in range(i + 1, min(i + 3, len(lines))):
            candidate = lines[j].strip()
            if candidate:
                title = candidate
                break
        if not title or len(title) > 110:
            continue
        # A heading names a thing; a body line finishes a sentence.
        if title.endswith((".", ";", ":", ",")):
            continue
        if len(title.split()) > 16:
            continue
        out.append((i, m.group(1), title))
    return out


def _split_by_subsections(section, max_chars):
    """Split a long section at its lettered subsection headings.

    Each child records its own absolute line span so its page range is
    computed from the document, not inherited from the parent. A 100-page
    parent section would otherwise stamp every child with the same useless
    span.
    """
    subs = find_subsections(section.text)
    if len(subs) < 2:
        return None

    lines = section.text.split("\n")
    pieces = []
    for idx, (line_no, letter, title) in enumerate(subs):
        stop = subs[idx + 1][0] if idx + 1 < len(subs) else len(lines)
        body = "\n".join(lines[line_no:stop]).strip()
        if body:
            pieces.append({
                "label": f"{letter}. {title}",
                "body": body,
                "line_no": line_no,
                "stop": stop,
            })

    if not pieces:
        return None

    page_map = section.page_map
    out = []
    for piece in pieces:
        abs_start = section.line_start + piece["line_no"]
        abs_end = section.line_start + piece["stop"] - 1

        if page_map:
            start_page = page_map[min(abs_start, len(page_map) - 1)]
            end_page = page_map[min(abs_end, len(page_map) - 1)]
        else:
            start_page, end_page = section.start_page, section.end_page

        child = Section(
            number=section.number,
            title=(f"{section.title} - {piece['label']}"
                   if section.title else piece["label"]),
            text=piece["body"],
            start_page=start_page,
            end_page=end_page,
            is_sequence=section.is_sequence,
            line_start=abs_start,
            page_map=page_map,
        )
        # A single subsection can still exceed the budget; fall back to
        # paragraphs, which keeps the narrowed page range already computed.
        if len(child.text) > max_chars:
            out.extend(_split_by_paragraphs(child, max_chars))
        else:
            out.append(child)
    return out


def _split_oversized(section, max_chars):
    """Break one very long section into smaller chunks.

    Prefer the document's own subsection headings, which keep each chunk
    aligned to one system and give it a meaningful label. Only fall back to
    paragraph splitting when no subsection structure exists, since labels
    like "part 2 of 5" carry no provenance value.
    """
    by_subsection = _split_by_subsections(section, max_chars)
    if by_subsection:
        return by_subsection
    return _split_by_paragraphs(section, max_chars)


def _split_by_paragraphs(section, max_chars):
    """Last-resort split at paragraph boundaries.

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
            line_start=section.line_start,
            page_map=section.page_map,
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
