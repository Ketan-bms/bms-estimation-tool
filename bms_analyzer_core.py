"""
bms_analyzer_core.py - PRODUCTION MVP
Core module for BMS estimation automation
Parses SOO → Generates scope, point list, labor estimate
"""

import fitz  # PyMuPDF
import hashlib
import json
import re
from anthropic import Anthropic


class BMSAnalyzer:
    """Main analyzer class - orchestrates all analysis"""
    
    def __init__(self, api_key, cache=None, extraction_model=None,
                 overview_model=None):
        # Defensive strip: a trailing space/newline on a pasted key produces an
        # illegal HTTP header and surfaces as an opaque APIConnectionError.
        self.client = Anthropic(api_key=(api_key or "").strip())
        self.soo_text = ""
        self.spec_text = ""
        self.analysis_results = {}
        self.point_list_truncated = False
        self.section_results_truncated = False
        self.analysis_truncated = False
        self.section_results = []
        self.section_narratives = {}
        self.coverage = {}
        # Maps a hash of (section text + model + prompt version) to the
        # points already extracted from it. Re-running an unchanged document
        # then costs nothing, which matters because iterating on the rest of
        # the pipeline would otherwise re-pay for extraction every time.
        self.cache = {} if cache is None else cache
        self.cache_hits = 0
        # Real usage as reported by the API, tracked per model since
        # extraction and overview calls are billed at different rates.
        # Populated on every non-cached call.
        self.usage = {
            "extraction": {"input_tokens": 0, "output_tokens": 0, "requests": 0},
            "overview": {"input_tokens": 0, "output_tokens": 0, "requests": 0},
        }
        if extraction_model:
            self.EXTRACTION_MODEL = extraction_model
        if overview_model:
            self.OVERVIEW_MODEL = overview_model
    
    # ============================================================================
    # STEP 1: PDF TEXT EXTRACTION
    # ============================================================================
    
    @staticmethod
    def extract_pdf_text(pdf_path):
        """Extract all text from a PDF, tagging each page.

        Static so the UI can read a document for the structure preview
        without constructing an analyzer or supplying an API key.
        """
        try:
            doc = fitz.open(pdf_path)
            text = ""
            for page_num, page in enumerate(doc, 1):
                page_text = page.get_text()
                text += f"\n--- PAGE {page_num} ---\n{page_text}"
            doc.close()

            # Drop repeated page headers and footers. They are sent with
            # every chunk and paid for every time, and contain no sequence
            # content.
            from soo_chunker import strip_page_furniture
            return strip_page_furniture(text)
        except Exception as e:
            return f"ERROR extracting PDF: {str(e)}"
    
    _ADDRESS_LINE = re.compile(
        r'^\s*(\d+[A-Za-z0-9\s\.]*?\b(?:Avenue|Ave|Street|St|Road|Rd|'
        r'Boulevard|Blvd|Drive|Dr|Lane|Ln|Place|Pl|Court|Ct|Way|Parkway|'
        r'Pkwy|Highway|Hwy|Terrace|Ter|Circle|Cir|Square|Sq)\.?)\s*'
        r'(?:,.*)?$',
        re.IGNORECASE,
    )

    @classmethod
    def extract_project_name(cls, pdf_path):
        """Find the building/project name from the document's own header.

        A specification's cover text almost always states the building
        address a few lines from the top, e.g. "655 Madison Avenue, New
        York, New York" or "175 Park Avenue" followed by "New York, New
        York" on the next line - well before any section numbering starts.
        That is a far better default project name than the uploaded
        filename, which is usually a spec section number like
        "230993_Sequence_Of_Operations_For_HVAC_Controls".

        Reads the first page directly with its own fitz call, deliberately
        NOT via extract_pdf_text: that method runs strip_page_furniture,
        which removes any line repeating on most pages to cut API cost -
        and the address line is exactly that, since it repeats on every
        page as a running header. Using the already-stripped text would
        silently delete the one line this function needs. Returns None if
        nothing matches, so the caller falls back to the filename.
        """
        try:
            doc = fitz.open(pdf_path)
            first_page_text = doc[0].get_text()
            doc.close()
        except Exception:
            return None

        for line in first_page_text.split("\n")[:40]:
            m = cls._ADDRESS_LINE.match(line.strip())
            if m:
                return re.sub(r"\s+", " ", m.group(1)).strip()
        return None

    # ============================================================================
    # STEP 2: SCOPE ANALYSIS (Claude AI)
    # ============================================================================
    
    def analyze_document(self, soo_text, point_list, spec_text=""):
        """Scope, labour and RFI analysis in one call.

        These were originally three separate calls, each sending the entire
        document. On a large SOO that means the full text goes to the
        priciest model three times over - for a 300+ page specification
        that is roughly 250,000 input tokens for this stage alone, often
        exceeding the cost of every per-section extraction call combined.
        None of the three tasks needs its own read: scope, labour and RFI
        judgement can all be formed from one pass, so this sends the
        document once and asks for all three (or four, with spec_text) JSON
        blocks together.

        spec_text, if provided, adds a fourth analysis: equipment named in
        the controls spec that has no corresponding points in the SOO
        extraction - a device scheduled with no stated control sequence is
        a common source of scope that gets missed rather than excluded.
        This roughly doubles the size of this one call when used, since the
        spec is sent in full alongside the SOO.
        """
        total_points = sum(int(p.get('Qty', 1) or 1) for p in point_list)
        equipment_found = sorted({
            str(p.get("Equipment", "")).strip()
            for p in point_list if str(p.get("Equipment", "")).strip()
        })

        # Panels are already fixed deterministically when points are
        # extracted (see _clean_system_name) - the model must use these
        # exact strings as row keys, not invent its own, so the labor table
        # lines up with the point list in Excel without a fuzzy join.
        panels = sorted({
            str(p.get("Panel", "")).strip()
            for p in point_list if str(p.get("Panel", "")).strip()
        })
        panel_list_text = "\n".join(f"  - {p}" for p in panels) if panels else "  (none)"

        spec_block = ""
        spec_schema = ""
        spec_guidance = ""
        if spec_text.strip():
            spec_schema = ''',
  "spec_cross_check": {{
    "devices_without_sequence": [
      "Tag or description of equipment named in the spec with no matching point above"
    ]
  }}'''
            spec_guidance = f"""
- Spec cross-check: equipment already found in the SOO extraction is:
  {', '.join(equipment_found) if equipment_found else '(none extracted)'}
  Read the controls specification below and list equipment or device tags
  it names that do NOT appear in that list - these are devices that may be
  scheduled with no stated control sequence, a common source of scope that
  gets missed rather than deliberately excluded. Only list genuine
  equipment/device references, not general requirements text."""
            spec_block = f"""

CONTROLS SPECIFICATION (cross-check against the equipment list above):
{spec_text}"""

        prompt = f"""You are a BMS controls expert and estimator reviewing a
complete Sequence of Operations. {total_points} control points have already
been extracted from it section by section.

Produce {'FOUR' if spec_text.strip() else 'THREE'} analyses from a single
read of the document(s) below. Return ONLY this JSON object as COMPACT
JSON - no markdown, no commentary, and no indentation or line-break
whitespace between fields, since every extra character here is budget
taken away from a document with {len(panels)} systems to cover:

{{
  "scope": {{
    "project_overview": "Brief description of the building and systems",
    "systems_in_scope": ["System1", "System2"],
    "total_io_points_estimate": {total_points},
    "integration_requirements": ["BACnet", "Hardwired controls"],
    "scope_clarity": {{
      "clearly_in_scope": ["Item1"],
      "needs_clarification": ["Item2"],
      "explicitly_excluded": ["Item3"]
    }}
  }},
  "labor_estimate": {{
    "systems": [
      {{
        "panel": "pnl-EXACT PANEL NAME FROM THE LIST BELOW",
        "panel_fab_hours": 0,
        "eng_orig_hours": 0,
        "eng_copy_hours": 0,
        "soft_orig_hours": 0,
        "soft_copy_hours": 0,
        "screen_orig_hours": 0,
        "screen_copy_hours": 0,
        "startup_hours": 0,
        "commiss_hours": 0
      }}
    ],
    "assumptions": "Brief explanation, referencing complexity drivers below"
  }},
  "rfis": {{
    "rfis": ["Question that needs clarification"],
    "exclusions": ["Item explicitly NOT in BMS scope"],
    "risks": ["Risk if a clarification above is not resolved"]
  }}{spec_schema}
}}

Guidance:
- Scope: use {total_points} as the I/O estimate rather than recounting -
  it was produced by a dedicated section-by-section extraction pass and is
  more reliable than a count from a single read.
- Labour: one row per panel, using these EXACT panel names (do not
  rename, merge, or add panels):
{panel_list_text}
  For each panel, estimate hours for a SINGLE instance of that system:
    - panel_fab_hours: technician time to fabricate/wire the panel
    - eng_orig_hours: engineering time to design and document this system
      the first time
    - eng_copy_hours: engineering time to replicate that design for one
      additional identical unit, if this system repeats (should be well
      below eng_orig_hours - copying a proven design is far faster than
      originating one)
    - soft_orig_hours / soft_copy_hours: same original-vs-copy split for
      programming
    - screen_orig_hours / screen_copy_hours: same split for graphics/screens
    - startup_hours, commiss_hours: field startup and commissioning time
      per physical unit - these scale per unit with no copy discount,
      unlike engineering/software/graphics, since each physical unit needs
      its own hands-on time regardless of how many came before it
  How many actual instances of each panel exist (from "typical of N" style
  language in the SOO) is handled separately - estimate hours for one
  instance only. Do not multiply by quantity yourself.
- RFIs: flag genuine ambiguities, not routine scope. Note anything that
  reads as present in a schedule but without a stated sequence, since that
  is a common source of missed scope in BMS estimating.{spec_guidance}

DOCUMENT:
{soo_text}{spec_block}"""

        # Output now includes one labor row per panel, not a fixed 5-line
        # summary - scale the budget so a 58-system document (175+ page
        # SOOs) doesn't get its labor table truncated the same way the
        # point list would without per-section chunking.
        #
        # These numbers were raised after a real failure: the original
        # estimate (2500 base + 90/panel) undershot badly on a 58-panel
        # document, cutting the response off mid-RFI. Two things were
        # under-budgeted - long panel names inflate each labor row well
        # past the original per-row estimate, and nothing accounted for
        # RFI text, which turned out to run to full sentences per item,
        # not short phrases. Raised with real margin rather than a small
        # bump on top of a number that already proved wrong once.
        base_tokens = 3500
        per_panel_tokens = 220
        spec_tokens = 800 if spec_text.strip() else 0
        max_tokens = base_tokens + len(panels) * per_panel_tokens + spec_tokens

        message = self._call_claude(prompt, max_tokens=max_tokens)
        raw_text = self._extract_text(message)
        parsed = self._parse_analysis_response(raw_text, message)

        # A malformed or partial response should not silently produce three
        # empty sections; each key defaults independently so one bad block
        # does not erase the others.
        raw_labor = parsed.get("labor_estimate", {}) if isinstance(parsed, dict) else {}
        result = {
            "scope": parsed.get("scope", {}) if isinstance(parsed, dict) else {},
            "labor_estimate": self._finalize_labor(raw_labor, point_list),
            "rfis": parsed.get("rfis", {}) if isinstance(parsed, dict) else {},
        }
        if spec_text.strip():
            result["spec_cross_check"] = (
                parsed.get("spec_cross_check", {}) if isinstance(parsed, dict) else {}
            )
        return result

    def _finalize_labor(self, raw_labor, point_list):
        """Attach quantity and compute totals for the per-system labor table.

        The model estimates raw per-unit hours only. Quantity and every
        total shown to the user is computed here in Python, never trusted
        to the model - an LLM asked to both estimate hours and multiply
        them by a quantity is a needless source of arithmetic error on a
        number that directly drives a bid.

        Quantity per panel comes from the point list's own Qty field (the
        same "typical of N" signal already captured during extraction),
        not asked of the model a second time - reusing data already
        extracted keeps this free of any additional judgement call that
        could disagree with the point list.
        """
        qty_by_panel = {}
        for p in point_list:
            panel = str(p.get("Panel", "")).strip()
            if not panel:
                continue
            qty_by_panel[panel] = max(qty_by_panel.get(panel, 1), self._num_qty(p))

        systems = raw_labor.get("systems", []) if isinstance(raw_labor, dict) else []
        finalized = []
        role_totals = {"tech": 0.0, "eng": 0.0, "soft": 0.0, "gpc": 0.0}

        for row in systems:
            if not isinstance(row, dict):
                continue
            panel = str(row.get("panel", "")).strip()
            qty = qty_by_panel.get(panel, 1)

            def h(key):
                return self._num(row.get(key), default=0)

            panel_fab = h("panel_fab_hours")
            eng_orig, eng_copy = h("eng_orig_hours"), h("eng_copy_hours")
            soft_orig, soft_copy = h("soft_orig_hours"), h("soft_copy_hours")
            screen_orig, screen_copy = h("screen_orig_hours"), h("screen_copy_hours")
            startup, commiss = h("startup_hours"), h("commiss_hours")

            eng_total = eng_orig + eng_copy * max(qty - 1, 0)
            soft_total = soft_orig + soft_copy * max(qty - 1, 0)
            screen_total = screen_orig + screen_copy * max(qty - 1, 0)
            panel_fab_total = panel_fab * qty
            startup_total = startup * qty
            commiss_total = commiss * qty
            tech_total = panel_fab_total + startup_total + commiss_total

            finalized.append({
                "panel": panel,
                "quantity": qty,
                "panel_fab_hours": panel_fab,
                "eng_orig_hours": eng_orig,
                "eng_copy_hours": eng_copy,
                "soft_orig_hours": soft_orig,
                "soft_copy_hours": soft_copy,
                "screen_orig_hours": screen_orig,
                "screen_copy_hours": screen_copy,
                "startup_hours": startup,
                "commiss_hours": commiss,
                "tech_total": tech_total,
                "eng_total": eng_total,
                "soft_total": soft_total,
                "screen_total": screen_total,
                "system_total": tech_total + eng_total + soft_total + screen_total,
            })

            role_totals["tech"] += tech_total
            role_totals["eng"] += eng_total
            role_totals["soft"] += soft_total
            role_totals["gpc"] += screen_total

        grand_total = sum(role_totals.values())

        return {
            "systems": finalized,
            "role_totals": {k: round(v, 2) for k, v in role_totals.items()},
            "total_hours": round(grand_total, 2),
            "assumptions": raw_labor.get("assumptions", "") if isinstance(raw_labor, dict) else "",
        }

    @staticmethod
    def _num(value, default=0):
        """Coerce a model-supplied value to a number, tolerating strings,
        units, or blanks - the same defensive coercion used throughout the
        output layer, needed here too since labor hours go through the
        same untrusted-model-output path."""
        if isinstance(value, (int, float)):
            return value
        if value is None:
            return default
        cleaned = re.sub(r"[^0-9.\-]", "", str(value))
        try:
            return float(cleaned) if cleaned not in ("", "-", ".") else default
        except ValueError:
            return default

    def _parse_point_array(self, cleaned, stop_reason):
        """Parse the point-list array, salvaging a truncated response.

        A large SOO can produce more points than fit in one response. When
        that happens the array is cut off mid-object with no closing bracket,
        and a strict parse throws away every point that did arrive. Instead,
        trim back to the last complete object and close the array, so a
        partial list is still usable. self.point_list_truncated records that
        this happened so the caller can say so rather than quietly presenting
        a short list as if it were complete.
        """
        self.point_list_truncated = False

        start = cleaned.find('[')
        if start < 0:
            raise ValueError(
                "Point list: no JSON array in response (stop_reason=%s). "
                "First 500 chars:\n%s" % (stop_reason, cleaned[:500])
            )

        end = cleaned.rfind(']')
        if end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass  # fall through to salvage

        # No closing bracket, or the array was malformed: salvage.
        fragment = cleaned[start:]
        while True:
            last_obj = fragment.rfind('}')
            if last_obj == -1:
                raise ValueError(
                    "Point list: response was truncated before any complete "
                    "entry (stop_reason=%s). Nothing could be recovered."
                    % stop_reason
                )
            try:
                parsed = json.loads(fragment[:last_obj + 1] + ']')
                self.point_list_truncated = True
                return parsed
            except json.JSONDecodeError:
                # That object was itself incomplete; drop it and retry.
                fragment = fragment[:last_obj]
    
    # ============================================================================
    # STEP 3: POINT LIST GENERATION (Claude AI)
    # ============================================================================

    def generate_point_list(self, soo_text, progress_callback=None,
                            section_filter=None):
        """Extract control points section by section.

        One call per SOO section rather than one call for the whole document.
        Each response then has to enumerate only the points for a single
        system, which keeps it well inside its length limit, and every point
        carries the section and pages it came from so it can be checked
        against the source.

        progress_callback(done, total, label) is invoked before each section
        so the UI can report progress on a run that takes several minutes.
        section_filter, if given, restricts extraction to chunks whose
        label is in the set - used when the user has reviewed the detected
        structure and chosen to run only part of the document.
        """
        from soo_chunker import build_chunks, coverage_report

        chunks = build_chunks(soo_text)

        if section_filter is not None:
            wanted = set(section_filter)
            chunks = [c for c in chunks if c.label in wanted]
            if not chunks:
                raise ValueError("No sections selected for extraction.")

        self.coverage = coverage_report(soo_text, chunks)
        self.section_results = []
        self.section_narratives = {}

        all_points = []
        for i, chunk in enumerate(chunks, 1):
            if progress_callback:
                progress_callback(i - 1, len(chunks), chunk.label)

            try:
                key = self._cache_key(chunk)
                if key in self.cache:
                    cached = self.cache[key]
                    points = [dict(p) for p in cached.get("points", [])]
                    narrative = list(cached.get("narrative", []))
                    self.cache_hits += 1
                    status, detail = "cached", ""
                else:
                    points, narrative = self._extract_points_from_section(chunk)
                    self.cache[key] = {
                        "points": [dict(p) for p in points],
                        "narrative": list(narrative),
                    }
                    status, detail = "ok", ""
            except Exception as e:
                # One bad section must not discard the other sixteen. The
                # failure is recorded and reported, never swallowed.
                points, narrative, status, detail = [], [], "failed", str(e)[:300]

            for pt in points:
                pt["Panel"] = f"pnl-{self._clean_system_name(chunk.label)}"
                pt["Source_Section"] = chunk.label
                pt["Source_Pages"] = chunk.page_range
            all_points.extend(points)
            if narrative:
                self.section_narratives[chunk.label] = narrative

            self.section_results.append({
                "section": chunk.label,
                "pages": chunk.page_range,
                "chars": len(chunk.text),
                "points": len(points),
                "status": status,
                "detail": detail,
            })

        if progress_callback:
            progress_callback(len(chunks), len(chunks), "merging")

        merged = self._merge_points(all_points)
        self._assign_confidence(merged, chunks)
        return merged

    # Bump when the extraction prompt changes, so cached results from an
    # older prompt are not silently reused. Bumped for the narrative +
    # object-response-shape change - a cache entry from the old prompt is
    # a bare list, not the {"points":..., "narrative":...} shape the
    # caller now expects, and would break rather than just miss narrative.
    PROMPT_VERSION = "2"

    def _cache_key(self, chunk):
        payload = "|".join((self.PROMPT_VERSION, self.EXTRACTION_MODEL,
                            chunk.label, chunk.text))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _clean_system_name(label):
        """Strip section numbering/lettering from a chunk label for use as
        a panel name, e.g. "1.8 PRIMARY CONDENSER WATER SYSTEM" -> "PRIMARY
        CONDENSER WATER SYSTEM", or a subsectioned label like "3.2 SEQUENCE
        OF OPERATION - A. Energy Recovery Unit" -> "Energy Recovery Unit"
        (the innermost, most specific part of the label - a subsection is a
        more useful panel grouping than its parent section).

        Set once here rather than left to the model per point: every point
        extracted from the same chunk must share the exact same Panel
        value, and a model asked to produce that string independently for
        each point risks drifting between "pnl-Primary Condenser Water" on
        one point and "pnl-PCW System" on the next.
        """
        # Use the innermost segment if this is a subsection of a subsection.
        name = label.rsplit(" - ", 1)[-1]
        # Strip a leading numbered ("1.8 ") or lettered ("A. ", "AA. ") marker.
        name = re.sub(r'^\s*(\d+\.\d+|\d+|[A-Z]{1,2})\.?\s+', '', name)
        # Strip a trailing "(part N/M)" paragraph-split marker, if present.
        name = re.sub(r'\s*\(part \d+/\d+\)\s*$', '', name)
        return re.sub(r'\s+', ' ', name).strip() or "GENERAL"

    def _extract_points_from_section(self, chunk):
        """Run one extraction call scoped to a single SOO section.

        Extracts two things from the same read: the discrete control
        points (as before), and the section's own narrative scope
        sentences - "Furnish X", "Provide Y", "shall be displayed at BMS
        graphics" - which a real proposal states as prose, not as a bulleted
        point list. Both are grounded in the section's actual text; the
        narrative sentences must be copied near-verbatim, not composed,
        for the same reason point Evidence is verbatim: a scope commitment
        this tool did not actually read should not appear in a proposal
        as if it did.
        """
        prompt = f"""You are a BMS point list expert reading ONE section of a
Sequence of Operations.

SECTION: {chunk.label}
SOURCE PAGES: {chunk.page_range}

Return ONLY this JSON object, no prose and no code fences:

{{
  "narrative": [
    "Near-verbatim scope sentence from this section, e.g. what will be furnished, provided, or displayed"
  ],
  "points": [
    {{
      "Panel": "pnl-MER-1",
      "Equipment": "ASHP-1",
      "Point_Name": "Compressor Status",
      "Control Device": "Current Switch",
      "AI": "", "BI": "1", "AO": "", "BO": "",
      "Qty": "1",
      "Description": "Status indication from compressor",
      "Evidence": "short verbatim phrase from the text below that this point came from"
    }}
  ]
}}

Narrative rules:
- Pull the section's own scope-commitment sentences: what the contractor
  will furnish, provide, install, wire, monitor, or display - phrasing
  like "Furnish...", "Provide...", "shall be displayed at BMS graphics".
  Rephrase only lightly (drop numbering, fix pronouns like "the BMS
  contractor shall" -> "we will"); do not compose new scope language or
  summarize - if a sentence is not close to something actually written in
  the section, it does not belong here.
- Skip generic administrative sentences (references to other spec
  sections, coordination boilerplate) - only scope actually being
  committed to.
- If this section has no narrative scope sentences distinct from its
  points, return an empty list.

Point rules:
- Temperature, pressure, humidity, flow and position feedback = AI
- On/off status, alarms, proof, and command feedback = BI
- Modulating valve, damper and speed commands = AO
- Start/stop and enable commands = BO
- Set exactly one of AI/BI/AO/BO to "1"; leave the other three as ""
- A point with no true physical I/O type (a calculated/derived value like
  enthalpy or wet-bulb temperature computed from other points, not read
  from a device) still belongs in points - set AI/BI/AO/BO all to "" for
  it rather than forcing a false I/O type or omitting the point entirely.
- Control Device is the general TYPE of field device that implements this
  point - e.g. "Temperature Sensor", "Humidity Sensor", "Pressure
  Transmitter", "Current Switch", "Differential Pressure Switch",
  "Modulating Actuator", "Two-Position Actuator", "VFD", "Relay",
  "End Switch". For a calculated point with no field device, leave this
  blank. Infer it from the point's function and I/O type. Do NOT invent a
  manufacturer or model number - the SOO does not specify hardware
  makes/models, only the sequence text does, so a specific product name
  here would be fabricated, not extracted.
- Qty is the number of identical points; if the text says a quantity of
  equipment (for example "four pumps"), give the per-equipment point once
  and set Qty to that number
- Use equipment tags exactly as written in the text. Do not invent tags.
- Some sections describe system-level points with no specific equipment
  tag at all (e.g. a shared outside-air sensing station, not tied to one
  piece of tagged equipment). When the section genuinely names no tag,
  leave Equipment blank rather than inventing one - a blank tag on a
  genuinely tagless point is correct, not an error.
- Evidence must be copied verbatim from the section text, under 15 words
- Extract ONLY from the section text below. Do not add points from memory
  or from other systems you would expect to see.
- If this section describes no control points, return an empty points list.

SECTION TEXT:
{chunk.text}"""

        message = self._call_claude(prompt, max_tokens=8500,
                                    model=self.EXTRACTION_MODEL)
        text = self._extract_text(message).strip()
        if not text:
            raise ValueError("model returned no text")

        cleaned = re.sub(r'```json\s*', '', text)
        cleaned = re.sub(r'```\s*', '', cleaned)
        stop_reason = getattr(message, "stop_reason", "unknown")

        start = cleaned.find('{')
        if start < 0:
            raise ValueError(
                "Section extraction: no JSON object in response "
                "(stop_reason=%s). First 300 chars:\n%s"
                % (stop_reason, cleaned[:300])
            )
        cleaned = cleaned[start:]

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            parsed = self._salvage_balanced(cleaned)

            # If "points" itself was cut off mid-array, it never reached
            # depth 1 to count as a completed top-level key, so the salvage
            # above drops it entirely - the same failure mode seen with
            # labor_estimate.systems. Recover it directly by position
            # regardless of what happened to narrative around it.
            if parsed is None or not parsed.get("points"):
                points_start = self._find_value_start(cleaned, "points")
                if points_start is not None:
                    points_salvaged = self._salvage_balanced(cleaned[points_start:])
                    if points_salvaged:
                        parsed = parsed if isinstance(parsed, dict) else {}
                        parsed["points"] = points_salvaged
                        parsed.setdefault("narrative", [])

            if not parsed or "points" not in parsed:
                raise ValueError(
                    "Section extraction: response was truncated before "
                    "even one point finished (stop_reason=%s). "
                    "Last 300 chars:\n%s" % (stop_reason, cleaned[-300:])
                )
            self.point_list_truncated = True
            self.section_results_truncated = True

        if not isinstance(parsed, dict):
            raise ValueError("Section extraction: response was not a JSON object")

        points = parsed.get("points", [])
        narrative = parsed.get("narrative", [])
        if not isinstance(points, list):
            points = []
        if not isinstance(narrative, list):
            narrative = []

        return points, [str(n).strip() for n in narrative if str(n).strip()]

    def _merge_points(self, points):
        """Collapse exact repeats inside a section; keep cross-section repeats.

        The same point appearing twice in one section is a duplication in the
        response. The same point appearing in two sections is usually a real
        second instance (a typical sequence applied to two systems), so those
        are kept and flagged rather than deleted - silently dropping them
        would understate the count.
        """
        seen_in_section = {}
        merged = []

        for pt in points:
            key = (
                str(pt.get("Source_Section", "")).strip().upper(),
                str(pt.get("Equipment", "")).strip().upper(),
                str(pt.get("Point_Name", "")).strip().upper(),
            )
            if key in seen_in_section:
                continue
            seen_in_section[key] = True
            merged.append(pt)

        # Flag the same equipment+point occurring in more than one section.
        counts = {}
        for pt in merged:
            k = (str(pt.get("Equipment", "")).strip().upper(),
                 str(pt.get("Point_Name", "")).strip().upper())
            counts[k] = counts.get(k, 0) + 1

        for pt in merged:
            k = (str(pt.get("Equipment", "")).strip().upper(),
                 str(pt.get("Point_Name", "")).strip().upper())
            pt["Repeats_In_Sections"] = counts[k] if counts[k] > 1 else ""

        return merged

    def _assign_confidence(self, points, chunks):
        """Grade each point by how directly the source text supports it.

        high   - the evidence phrase is verbatim in its source section,
                 the I/O type is unambiguous, and if a tag is given it
                 appears verbatim too
        medium - evidence could not be corroborated, but nothing else
                 about the point looks wrong
        low    - a claimed equipment tag does NOT appear in the source
                 text (likely fabricated), more than one I/O type was
                 set, or the point spans multiple sections

        A blank Equipment tag is not itself a penalty. Some SOO sections
        describe system-level points with no tagged equipment at all - a
        shared outside-air sensing station, for example - and that is a
        correct absence, not a sign of a bad extraction. Only a tag that
        was actually given but does not appear in the text is treated as
        suspect. Likewise, zero I/O flags is valid for a calculated point
        (enthalpy, wet-bulb - derived from other points, not read from a
        device); only MORE than one flag set is a real ambiguity.
        """
        by_label = {c.label: c.text for c in chunks}

        for pt in points:
            source_text = by_label.get(pt.get("Source_Section", ""), "")
            tag = str(pt.get("Equipment", "")).strip()
            evidence = str(pt.get("Evidence", "")).strip()

            io_count = sum(1 for k in ("AI", "BI", "AO", "BO")
                          if str(pt.get(k, "")).strip())
            io_ambiguous = io_count > 1  # 0 is valid (calculated point)

            tag_suspect = bool(tag) and tag.upper() not in source_text.upper()
            evidence_found = bool(evidence) and evidence.lower() in source_text.lower()

            if tag_suspect or io_ambiguous or pt.get("Repeats_In_Sections"):
                pt["Confidence"] = "low"
            elif evidence_found:
                pt["Confidence"] = "high"
            else:
                pt["Confidence"] = "medium"

    # ============================================================================
    # UTILITY: JSON PARSER
    # ============================================================================
    
    # Per-section extraction is the bulk of the work: dozens of calls that
    # transcribe points already written in the text. Scope, labour and RFI
    # analysis are three calls that require judgement across the whole
    # document, so they stay on the stronger model.
    EXTRACTION_MODEL = "claude-sonnet-5"
    OVERVIEW_MODEL = "claude-opus-5"

    def _call_claude(self, prompt, max_tokens, model=None):
        """Send one prompt and return the completed Message.

        Uses the streaming API. The SDK refuses non-streaming requests whose
        max_tokens is large enough that they could exceed a 10 minute wall
        clock, which the point-list call does. Streaming also avoids proxy
        timeouts on long generations. get_final_message() reassembles the
        stream into the same Message object a create() call would return,
        so .content and .stop_reason behave identically downstream.
        """
        with self.client.messages.stream(
            model=model or self.OVERVIEW_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            message = stream.get_final_message()

        if getattr(message, "usage", None):
            bucket = "extraction" if model == self.EXTRACTION_MODEL else "overview"
            self.usage[bucket]["input_tokens"] += getattr(message.usage, "input_tokens", 0) or 0
            self.usage[bucket]["output_tokens"] += getattr(message.usage, "output_tokens", 0) or 0
            self.usage[bucket]["requests"] += 1

        return message

    def _extract_text(self, message):
        """Pull the text out of a Claude response.

        message.content is a list of blocks. With extended thinking enabled,
        block 0 is a ThinkingBlock (no .text attribute), so we filter for
        text blocks and join them rather than indexing blindly.
        """
        parts = []
        for block in message.content:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)
            elif hasattr(block, "text"):
                parts.append(block.text)
        return "\n".join(parts).strip()

    def _parse_analysis_response(self, text, message):
        """Parse the combined scope/labor/RFI response.

        This response scales with panel count (one labor row per system),
        so a document with many systems is the one most likely to hit its
        token budget mid-response. Two different truncation shapes have
        been seen on real documents:

        1. Truncated AFTER labor_estimate finished, mid-way through RFIs.
           Recovering complete top-level keys is enough here - scope and
           the full labor table are already done.
        2. Truncated INSIDE labor_estimate.systems itself, after dozens of
           complete panel rows but before the array closes. Top-level
           salvage alone fails this case: since labor_estimate never
           finishes, none of its rows count as a "complete top-level key",
           and every row that did arrive intact gets discarded along with
           the one that didn't.

        Case 2 is handled by locating the systems array directly by string
        position and salvaging it on its own, independent of whether the
        surrounding scope/labor_estimate/rfis structure is valid - so
        forty complete rows are kept even when row forty-one is not.
        self.analysis_truncated records that either path fired, so the
        caller can say so rather than presenting a partial result as
        complete.
        """
        self.analysis_truncated = False
        cleaned = re.sub(r'```json\s*', '', text.strip())
        cleaned = re.sub(r'```\s*', '', cleaned)

        start = cleaned.find('{')
        if start < 0:
            raise ValueError(
                "Combined analysis: no JSON object found in response "
                "(stop_reason=%s). First 300 chars:\n%s"
                % (getattr(message, "stop_reason", "unknown"), cleaned[:300])
            )
        cleaned = cleaned[start:]

        # Tier 1: full parse.
        end = cleaned.rfind('}')
        if end > 0:
            try:
                return json.loads(cleaned[:end + 1])
            except json.JSONDecodeError:
                pass

        # Tier 2: complete top-level keys (handles truncation after
        # labor_estimate has already finished).
        salvaged = self._salvage_balanced(cleaned)
        if salvaged is not None and salvaged.get("labor_estimate", {}).get("systems"):
            self.analysis_truncated = True
            return salvaged

        # Tier 3: labor_estimate.systems truncated mid-array. Recover the
        # array directly by position, then rebuild scope/labor_estimate
        # around it from whatever else salvaged cleanly.
        systems_start = self._find_value_start(cleaned, "systems")
        if systems_start is not None:
            systems = self._salvage_balanced(cleaned[systems_start:])
            if systems:
                self.analysis_truncated = True
                result = salvaged if isinstance(salvaged, dict) else {}
                result.setdefault("scope", {})
                result["labor_estimate"] = {
                    "systems": systems,
                    "assumptions": (result.get("labor_estimate") or {}).get("assumptions", ""),
                }
                result.setdefault("rfis", {})
                return result

        raise ValueError(
            "Combined analysis: JSON was malformed and nothing could be "
            "salvaged (stop_reason=%s). This usually means the response "
            "was truncated before even one labor row finished - most "
            "likely this document's panel count exceeds the current "
            "token budget by a wide margin. Last 300 chars:\n%s"
            % (getattr(message, "stop_reason", "unknown"), cleaned[-300:])
        )

    @staticmethod
    def _salvage_balanced(text):
        """Recover the largest valid JSON value from text that starts with
        '{' or '[' and may be truncated mid-way through.

        Generalizes the point-list array salvage to work on either an
        object or an array root, and to be callable on ANY bracketed
        substring - not just the response's outer object. That matters
        because truncation does not always happen conveniently between
        top-level keys: a document with enough panels can get cut off
        mid-way through the labor_estimate.systems array itself, after
        dozens of complete rows. Salvaging only whole top-level keys would
        then discard the entire labor table, including every row that
        arrived intact, because "labor_estimate" itself never finished.
        Calling this directly on the systems array's own text recovers
        those rows regardless of what happened elsewhere in the response.

        Tracks bracket depth and string state (respecting escaped quotes,
        so a literal '}' inside a string value is not mistaken for a real
        closing bracket). Every time depth returns to 1 - back at the
        root value's own level - a child element has just finished, and
        that position is recorded. If the root itself closes cleanly, the
        full value is returned. Otherwise, whatever comes after the last
        recorded position is an incomplete trailing element and is cut,
        not repaired.
        """
        if not text or text[0] not in "{[":
            return None
        closing = "}" if text[0] == "{" else "]"

        depth = 0
        in_string = False
        escape = False
        last_complete_end = None

        for i, ch in enumerate(text):
            if in_string:
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch in '{[':
                depth += 1
            elif ch in '}]':
                depth -= 1
                if depth == 1:
                    last_complete_end = i + 1
                elif depth == 0:
                    # Root closed cleanly - no salvage needed, this is a
                    # complete value in its own right.
                    try:
                        return json.loads(text[:i + 1])
                    except json.JSONDecodeError:
                        pass
            elif ch == ',' and depth == 1:
                last_complete_end = i

        if last_complete_end is None:
            return None

        candidate = text[:last_complete_end].rstrip()
        if candidate.endswith(','):
            candidate = candidate[:-1]
        candidate += closing

        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _find_value_start(text, key):
        """Find where a JSON key's value begins (the '{' or '[' right
        after "key":), returning None if that key isn't present. Used to
        locate a nested value (like labor_estimate.systems) directly in
        raw text, without needing the surrounding JSON to be valid."""
        m = re.search(r'"%s"\s*:\s*' % re.escape(key), text)
        if not m:
            return None
        return m.end()

    def _parse_json_response(self, text):
        """Parse JSON from Claude response, handling markdown"""
        try:
            text = text.strip()
            # Remove markdown code blocks
            text = re.sub(r'```json\s*', '', text)
            text = re.sub(r'```\s*', '', text)
            
            # Find JSON object or array
            start = text.find('{')
            if start == -1:
                start = text.find('[')
            end = text.rfind('}')
            if end == -1:
                end = text.rfind(']') + 1
            
            if start >= 0 and end > start:
                json_str = text[start:end+1]
                return json.loads(json_str)
        except:
            pass
        
        return {}
    
    # ============================================================================
    # MAIN: RUN COMPLETE ANALYSIS
    # ============================================================================
    
    @staticmethod
    def _num_qty(point):
        """Qty as an int, tolerating strings and blanks."""
        raw = point.get("Qty", 1)
        try:
            return int(float(str(raw).strip() or 1))
        except (TypeError, ValueError):
            return 1

    def run_full_analysis(self, soo_pdf_path, spec_pdf_path=None,
                          progress_callback=None, section_filter=None):
        """Run the full pipeline.

        progress_callback(done, total, label) is forwarded to the point-list
        stage, which is the long one: it makes one call per SOO section.
        """
        def step(label):
            if progress_callback:
                progress_callback(0, 0, label)

        step("Reading PDF")
        self.soo_text = self.extract_pdf_text(soo_pdf_path)
        if spec_pdf_path:
            self.spec_text = self.extract_pdf_text(spec_pdf_path)

        points = self.generate_point_list(
            self.soo_text,
            progress_callback=progress_callback,
            section_filter=section_filter,
        )

        step("Analysing scope, labour and RFIs")
        # One call over the whole document rather than three. It runs after
        # extraction so the point count it is given is the real one, not a
        # second guess from a single read.
        analysis = self.analyze_document(self.soo_text, points, spec_text=self.spec_text)
        scope = analysis["scope"]
        labor = analysis["labor_estimate"]
        rfis = analysis["rfis"]
        
        # Compile all results
        self.analysis_results = {
            "scope": scope,
            "point_list": points,
            "labor_estimate": labor,
            "rfis": rfis,
            "section_narratives": self.section_narratives,
            "metadata": {
                "soo_pages": self.soo_text.count("--- PAGE"),
                "soo_characters": len(self.soo_text),
                "point_list_truncated": self.section_results_truncated,
                "analysis_truncated": self.analysis_truncated,
                "total_points_extracted": len(points),
                "total_i_o_count": sum(self._num_qty(p) for p in points),
                "coverage": self.coverage,
                "sections": self.section_results,
                "sections_failed": [r for r in self.section_results
                                    if r["status"] not in ("ok", "cached")],
                "sections_cached": sum(1 for r in self.section_results
                                       if r["status"] == "cached"),
                "usage": dict(self.usage),
                "confidence_counts": {
                    level: sum(1 for p in points if p.get("Confidence") == level)
                    for level in ("high", "medium", "low")
                },
            }
        }
        
        return self.analysis_results


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    import os
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    
    analyzer = BMSAnalyzer(api_key)
    
    # Run analysis
    results = analyzer.run_full_analysis(
        soo_pdf_path="/path/to/soo.pdf",
        spec_pdf_path="/path/to/spec.pdf"
    )
    
    # Save results
    with open("analysis_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print("✅ Analysis complete! Results saved to analysis_results.json")
