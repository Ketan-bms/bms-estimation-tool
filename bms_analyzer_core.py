"""
bms_analyzer_core.py - PRODUCTION MVP
Core module for BMS estimation automation
Parses SOO → Generates scope, point list, labor estimate
"""

import fitz  # PyMuPDF
import json
import re
from anthropic import Anthropic


class BMSAnalyzer:
    """Main analyzer class - orchestrates all analysis"""
    
    def __init__(self, api_key):
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
    
    # ============================================================================
    # STEP 1: PDF TEXT EXTRACTION
    # ============================================================================
    
    def extract_pdf_text(self, pdf_path):
        """Extract all text from PDF file"""
        try:
            doc = fitz.open(pdf_path)
            text = ""
            for page_num, page in enumerate(doc, 1):
                page_text = page.get_text()
                text += f"\n--- PAGE {page_num} ---\n{page_text}"
            doc.close()
            return text
        except Exception as e:
            return f"ERROR extracting PDF: {str(e)}"
    
    # ============================================================================
    # STEP 2: SCOPE ANALYSIS (Claude AI)
    # ============================================================================
    
    def analyze_scope_overview(self, soo_text):
        """Claude reads SOO and generates scope overview"""
        
        prompt = f"""You are a BMS controls expert. Analyze this Sequence of Operations document.

Extract and provide:
1. Project Overview: What building/systems are being controlled?
2. Systems Included: List all HVAC/BMS systems in scope (AHU, DOAS, ASHP, chillers, ERU, VAV, etc)
3. Total I/O Points Estimate: Count approximate I/O points from the SOO
4. Integration Requirements: BACnet, hardwired, fire interface, etc.
5. Scope Status: Clearly included vs needs clarification

Return ONLY valid JSON (no markdown, no code blocks):

{{
  "project_overview": "Brief description",
  "systems_in_scope": ["System1", "System2"],
  "total_io_points_estimate": 150,
  "integration_requirements": ["BACnet", "Hardwired controls"],
  "scope_clarity": {{
    "clearly_in_scope": ["Item1"],
    "needs_clarification": ["Item2"],
    "explicitly_excluded": ["Item3"]
  }}
}}

SOO TEXT (first 5000 chars - summary):
{soo_text}

This is the complete SOO. Cover every system described anywhere in it."""
        
        message = self._call_claude(prompt, max_tokens=4000)
        
        return self._parse_json_response(self._extract_text(message))
    
    # ============================================================================
    # STEP 3: POINT LIST GENERATION (Claude AI)
    # ============================================================================
    
    def generate_point_list(self, soo_text, progress_callback=None):
        """Extract control points section by section.

        One call per SOO section rather than one call for the whole document.
        Each response then has to enumerate only the points for a single
        system, which keeps it well inside its length limit, and every point
        carries the section and pages it came from so it can be checked
        against the source.

        progress_callback(done, total, label) is invoked before each section
        so the UI can report progress on a run that takes several minutes.
        """
        from soo_chunker import build_chunks, coverage_report

        chunks = build_chunks(soo_text)
        self.coverage = coverage_report(soo_text, chunks)
        self.section_results = []

        all_points = []
        for i, chunk in enumerate(chunks, 1):
            if progress_callback:
                progress_callback(i - 1, len(chunks), chunk.label)

            try:
                points = self._extract_points_from_section(chunk)
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

        message = self._call_claude(prompt, max_tokens=8000)
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

        This mirrors the device-level rule of grading on verbatim support
        rather than plausibility, applied here at point level.
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
    # STEP 4: LABOR ESTIMATION (Claude AI)
    # ============================================================================
    
    def estimate_labor_hours(self, soo_text, point_list):
        """Claude estimates labor hours based on complexity"""
        
        total_points = sum(int(p.get('Qty', 1) or 1) for p in point_list)
        
        prompt = f"""You are a BMS labor estimator. Estimate labor hours for this project.

Project Statistics:
- Total I/O Points: {total_points}
- System Complexity: Analyze from SOO

SOO Summary:
{soo_text}

Estimate hours for these roles (realistic NYC/Boston market, 2025):
1. Engineering & Design (20-50 hrs)
2. Controls Programming (30-100 hrs)  
3. Field Installation & Wiring (40-150 hrs)
4. System Testing & Commissioning (15-50 hrs)
5. Operator Training (5-20 hrs)

Return ONLY valid JSON (no markdown):

{{
  "labor_estimate": {{
    "engineering": {{"hours": 0, "rate": 150}},
    "programming": {{"hours": 0, "rate": 160}},
    "installation": {{"hours": 0, "rate": 120}},
    "testing": {{"hours": 0, "rate": 140}},
    "training": {{"hours": 0, "rate": 120}}
  }},
  "total_hours": 0,
  "total_labor_cost": 0,
  "assumptions": "Brief explanation"
}}

Consider:
- Complexity from SOO (VFD drives, ERU, multi-chiller, water loops = more complex)
- Number of I/O points ({total_points} points estimated)
- Integration requirements
- Risk factors"""
        
        message = self._call_claude(prompt, max_tokens=3000)
        
        return self._parse_json_response(self._extract_text(message))
    
    # ============================================================================
    # STEP 5: RFI & EXCLUSIONS DETECTION
    # ============================================================================
    
    def detect_rfis_and_exclusions(self, soo_text):
        """Claude identifies missing/unclear items and exclusions"""
        
        prompt = f"""You are a BMS controls specialist. Review this SOO and identify:

1. RFIs (Requests for Information) - items that need clarification
2. Exclusions - what's explicitly NOT in BMS scope
3. Risk Items - what could cause problems if missed

SOO:
{soo_text}

Return ONLY valid JSON:

{{
  "rfis": [
    "Question 1 that needs clarification",
    "Question 2"
  ],
  "exclusions": [
    "Item explicitly NOT in BMS scope",
    "Another exclusion"
  ],
  "risks": [
    "Risk if this isn't clarified",
    "Another risk"
  ]
}}"""
        
        message = self._call_claude(prompt, max_tokens=3000)
        
        return self._parse_json_response(self._extract_text(message))
    
    # ============================================================================
    # UTILITY: JSON PARSER
    # ============================================================================
    
    MODEL = "claude-opus-5"

    def _call_claude(self, prompt, max_tokens):
        """Send one prompt and return the completed Message.

        Uses the streaming API. The SDK refuses non-streaming requests whose
        max_tokens is large enough that they could exceed a 10 minute wall
        clock, which the point-list call does. Streaming also avoids proxy
        timeouts on long generations. get_final_message() reassembles the
        stream into the same Message object a create() call would return,
        so .content and .stop_reason behave identically downstream.
        """
        with self.client.messages.stream(
            model=self.MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            return stream.get_final_message()

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
                          progress_callback=None):
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

        step("Analysing scope")
        scope = self.analyze_scope_overview(self.soo_text)

        points = self.generate_point_list(
            self.soo_text, progress_callback=progress_callback
        )

        step("Estimating labour")
        labor = self.estimate_labor_hours(self.soo_text, points)

        step("Detecting RFIs")
        rfis = self.detect_rfis_and_exclusions(self.soo_text)
        
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
                                    if r["status"] != "ok"],
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
