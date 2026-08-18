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
        self.section_results = []
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
    
    # ============================================================================
    # STEP 2: SCOPE ANALYSIS (Claude AI)
    # ============================================================================
    
    def analyze_document(self, soo_text, point_list):
        """Scope, labour and RFI analysis in one call.

        These were originally three separate calls, each sending the entire
        document. On a large SOO that means the full text goes to the
        priciest model three times over - for 175 Park's ~335,000 characters
        that is roughly 250,000 input tokens for this stage alone, often
        exceeding the cost of every per-section extraction call combined.
        None of the three tasks needs its own read: scope, labour and RFI
        judgement can all be formed from one pass, so this sends the
        document once and asks for all three JSON blocks together.
        """
        total_points = sum(int(p.get('Qty', 1) or 1) for p in point_list)

        prompt = f"""You are a BMS controls expert and estimator reviewing a
complete Sequence of Operations. {total_points} control points have already
been extracted from it section by section.

Produce THREE analyses from a single read of the document below. Return
ONLY this JSON object, no markdown, no commentary:

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
    "labor_estimate": {{
      "engineering": {{"hours": 0}},
      "programming": {{"hours": 0}},
      "installation": {{"hours": 0}},
      "testing": {{"hours": 0}},
      "training": {{"hours": 0}}
    }},
    "total_hours": 0,
    "assumptions": "Brief explanation, referencing complexity drivers below"
  }},
  "rfis": {{
    "rfis": ["Question that needs clarification"],
    "exclusions": ["Item explicitly NOT in BMS scope"],
    "risks": ["Risk if a clarification above is not resolved"]
  }}
}}

Guidance:
- Scope: use {total_points} as the I/O estimate rather than recounting -
  it was produced by a dedicated section-by-section extraction pass and is
  more reliable than a count from a single read.
- Labour: base hours on realistic NYC/Boston market rates. Weight for
  complexity drivers - VFDs, ERUs, multiple chiller or condenser water
  loops - and for point volume ({total_points} points).
- RFIs: flag genuine ambiguities, not routine scope. Note anything that
  reads as present in a schedule but without a stated sequence, since that
  is a common source of missed scope in BMS estimating.

DOCUMENT:
{soo_text}"""

        message = self._call_claude(prompt, max_tokens=3500)
        parsed = self._parse_json_response(self._extract_text(message))

        # A malformed or partial response should not silently produce three
        # empty sections; each key defaults independently so one bad block
        # does not erase the others.
        return {
            "scope": parsed.get("scope", {}) if isinstance(parsed, dict) else {},
            "labor_estimate": parsed.get("labor_estimate", {}) if isinstance(parsed, dict) else {},
            "rfis": parsed.get("rfis", {}) if isinstance(parsed, dict) else {},
        }

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

        all_points = []
        for i, chunk in enumerate(chunks, 1):
            if progress_callback:
                progress_callback(i - 1, len(chunks), chunk.label)

            try:
                key = self._cache_key(chunk)
                if key in self.cache:
                    points = [dict(p) for p in self.cache[key]]
                    self.cache_hits += 1
                    status, detail = "cached", ""
                else:
                    points = self._extract_points_from_section(chunk)
                    self.cache[key] = [dict(p) for p in points]
                    status, detail = "ok", ""
            except Exception as e:
                # One bad section must not discard the other sixteen. The
                # failure is recorded and reported, never swallowed.
                points, status, detail = [], "failed", str(e)[:300]

            for pt in points:
                pt["Source_Section"] = chunk.label
                pt["Source_Pages"] = chunk.page_range
            all_points.extend(points)

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
    # older prompt are not silently reused.
    PROMPT_VERSION = "1"

    def _cache_key(self, chunk):
        payload = "|".join((self.PROMPT_VERSION, self.EXTRACTION_MODEL,
                            chunk.label, chunk.text))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _extract_points_from_section(self, chunk):
        """Run one extraction call scoped to a single SOO section."""
        prompt = f"""You are a BMS point list expert reading ONE section of a
Sequence of Operations. Extract every control point described in this section.

SECTION: {chunk.label}
SOURCE PAGES: {chunk.page_range}

Return ONLY a JSON array, no prose and no code fences:

[
  {{
    "Panel": "pnl-MER-1",
    "Equipment": "ASHP-1",
    "Point_Name": "Compressor Status",
    "AI": "", "BI": "1", "AO": "", "BO": "",
    "Qty": "1",
    "Description": "Status indication from compressor",
    "Evidence": "short verbatim phrase from the text below that this point came from"
  }}
]

Rules:
- Temperature, pressure, humidity, flow and position feedback = AI
- On/off status, alarms, proof, and command feedback = BI
- Modulating valve, damper and speed commands = AO
- Start/stop and enable commands = BO
- Set exactly one of AI/BI/AO/BO to "1"; leave the other three as ""
- Qty is the number of identical points; if the text says a quantity of
  equipment (for example "four pumps"), give the per-equipment point once
  and set Qty to that number
- Use equipment tags exactly as written in the text. Do not invent tags.
- Evidence must be copied verbatim from the section text, under 15 words
- Extract ONLY from the section text below. Do not add points from memory
  or from other systems you would expect to see.
- If this section describes no control points, return []

SECTION TEXT:
{chunk.text}"""

        message = self._call_claude(prompt, max_tokens=8000,
                                    model=self.EXTRACTION_MODEL)
        text = self._extract_text(message).strip()
        if not text:
            raise ValueError("model returned no text")

        cleaned = re.sub(r'```json\s*', '', text)
        cleaned = re.sub(r'```\s*', '', cleaned)
        stop_reason = getattr(message, "stop_reason", "unknown")

        points = self._parse_point_array(cleaned, stop_reason)
        if self.point_list_truncated:
            # Sized to avoid this, so if it happens the section is unusually
            # dense and the caller needs to know rather than assume.
            self.section_results_truncated = True
        return points

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

        high   - equipment tag appears verbatim in its source section, the
                 evidence phrase is present in that text, and exactly one
                 I/O type is set
        medium - tag is verbatim but the classification or evidence could
                 not be corroborated
        low    - tag does not appear in the source text, or the point spans
                 multiple sections, or no single I/O type was assigned
        """
        by_label = {c.label: c.text for c in chunks}

        for pt in points:
            source_text = by_label.get(pt.get("Source_Section", ""), "")
            tag = str(pt.get("Equipment", "")).strip()
            evidence = str(pt.get("Evidence", "")).strip()

            io_flags = [pt.get(k) for k in ("AI", "BI", "AO", "BO")]
            single_io = sum(1 for f in io_flags if str(f).strip()) == 1

            tag_verbatim = bool(tag) and tag.upper() in source_text.upper()
            evidence_found = bool(evidence) and evidence.lower() in source_text.lower()

            if not tag_verbatim or not single_io or pt.get("Repeats_In_Sections"):
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
        analysis = self.analyze_document(self.soo_text, points)
        scope = analysis["scope"]
        labor = analysis["labor_estimate"]
        rfis = analysis["rfis"]
        
        # Compile all results
        self.analysis_results = {
            "scope": scope,
            "point_list": points,
            "labor_estimate": labor,
            "rfis": rfis,
            "metadata": {
                "soo_pages": self.soo_text.count("--- PAGE"),
                "soo_characters": len(self.soo_text),
                "point_list_truncated": self.section_results_truncated,
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
