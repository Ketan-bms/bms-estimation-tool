# BMS Cost Estimation Tool

An AI-powered cost estimation system for Building Management Systems (BMS) projects.

## Problem
Construction teams spend 8+ hours manually estimating BMS project costs from unstructured PDFs. It's error-prone, time-consuming, and expensive.

## Solution
Multi-stage LLM pipeline that automatically generates:
- **Take-offs** (equipment costs from scanned documents)
- **Labor schedules** (hours required per point)
- **SOO discrepancy detection** (gaps between contract scope and drawings)

From messy, unstructured PDFs to structured, actionable data.

## Architecture

**Stage 1: Document Parsing**
- Tesseract OCR extracts text from PDFs
- Claude API processes raw text into structured format

**Stage 2: Cost Estimation**
- GPT-4 analyzes equipment lists, quantities, specifications
- Domain logic applies labor hour norms (Python-based calculation)

**Stage 3: Validation & Reporting**
- Discrepancy detection against Standards of Operation (SOO)
- JSON export for integration with project management tools

## Tech Stack
- **LLM & API:** Claude API, GPT-4
- **Computer Vision:** Tesseract OCR
- **Backend:** Python
- **UI:** Streamlit
- **Deployment:** Docker container

## Key Features
- ✅ Automated take-off generation from PDF
- ✅ Labor hour estimation (deterministic + domain rules)
- ✅ SOO discrepancy flagging
- ✅ Structured JSON output

## Impact
- **60%+ reduction** in manual estimation time (8 hours → 90 minutes)
- **Higher accuracy** through systematic discrepancy detection
- **Scalable** across projects and teams

## Files
- `app.py` - Main application
- `pdf_takeoff.py` - PDF processing + take-off generation
- `schedule_extractor.py` - Labor schedule extraction
- `discrepancy_check.py` - SOO validation logic
- `material_module.py` - Material/equipment database
- `drawing_markup.py` - Visual markup generation

## How to Use
1. Upload BMS PDF
2. Tool generates take-off, labor schedule, discrepancies
3. Export as JSON

## Future Roadmap
- Computer vision enhancement (YOLO v2) for equipment detection
- Real-time feedback on estimation accuracy
- Integration with project management platforms (Procore, etc.)
