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
        
        message = self.client.messages.create(
            model="claude-opus-5",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return self._parse_json_response(self._extract_text(message))
    
    # ============================================================================
    # STEP 3: POINT LIST GENERATION (Claude AI)
    # ============================================================================
    
    def generate_point_list(self, soo_text):
        """Claude generates point list from SOO"""
        
        prompt = f"""You are a BMS point list expert. Extract all control points from this SOO.

Generate a point list in JSON array format with these columns:
- Panel: Control panel name (e.g., "pnl-MER-1")
- Equipment: Equipment tag (e.g., "ASHP-1", "AHU-3")
- Point_Name: Descriptive point name
- AI: 1 if Analog Input, blank otherwise
- BI: 1 if Binary Input (Digital Input), blank otherwise  
- AO: 1 if Analog Output, blank otherwise
- BO: 1 if Binary Output (Digital Output), blank otherwise
- Qty: Quantity of this point (usually 1)
- Description: What this point does

Return ONLY valid JSON array (no markdown):

[
  {{
    "Panel": "pnl-MER-1",
    "Equipment": "ASHP-1",
    "Point_Name": "Compressor Status",
    "AI": "",
    "BI": "1",
    "AO": "",
    "BO": "",
    "Qty": "1",
    "Description": "Status indication from compressor"
  }}
]

Extract from SOO:
{soo_text}

Rules:
- Temperature/pressure/humidity sensors = AI
- On/off status, alarms = BI
- Valve commands, damper commands = AO
- Relay outputs, pump start = BO
- Qty = count of same point type (e.g., 3 fans = 3x supply fan start)
- Return ONLY the JSON array, nothing else"""
        
        message = self.client.messages.create(
            model="claude-opus-5",
            max_tokens=32000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = self._extract_text(message).strip()

        if not response_text:
            raise ValueError(
                "Point list: model returned no text. "
                "Response blocks: %s" % [getattr(b, "type", "?") for b in message.content]
            )

        cleaned = re.sub(r'```json\s*', '', response_text)
        cleaned = re.sub(r'```\s*', '', cleaned)

        start = cleaned.find('[')
        end = cleaned.rfind(']') + 1
        if start < 0 or end <= start:
            raise ValueError(
                "Point list: no JSON array found in response. "
                "First 500 chars:\n%s" % cleaned[:500]
            )

        try:
            return json.loads(cleaned[start:end])
        except json.JSONDecodeError as e:
            # Most likely cause: response hit max_tokens and the array was
            # cut off mid-object. Say so rather than returning an empty list.
            raise ValueError(
                "Point list: JSON was malformed (%s). This usually means the "
                "response was truncated - stop_reason was '%s'. Last 300 chars:\n%s"
                % (e, getattr(message, "stop_reason", "unknown"), cleaned[-300:])
            )
    
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
        
        message = self.client.messages.create(
            model="claude-opus-5",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        
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
        
        message = self.client.messages.create(
            model="claude-opus-5",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return self._parse_json_response(self._extract_text(message))
    
    # ============================================================================
    # UTILITY: JSON PARSER
    # ============================================================================
    
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
    
    def run_full_analysis(self, soo_pdf_path, spec_pdf_path=None):
        """Run complete analysis pipeline"""
        
        print("🔄 Step 1: Extracting text from PDFs...")
        self.soo_text = self.extract_pdf_text(soo_pdf_path)
        if spec_pdf_path:
            self.spec_text = self.extract_pdf_text(spec_pdf_path)
        
        print("🔄 Step 2: Analyzing scope overview...")
        scope = self.analyze_scope_overview(self.soo_text)
        
        print("🔄 Step 3: Generating point list...")
        points = self.generate_point_list(self.soo_text)
        
        print("🔄 Step 4: Estimating labor hours...")
        labor = self.estimate_labor_hours(self.soo_text, points)
        
        print("🔄 Step 5: Detecting RFIs & exclusions...")
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
                "total_points_extracted": len(points),
                "total_i_o_count": sum(int(p.get('Qty', 1) or 1) for p in points)
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
