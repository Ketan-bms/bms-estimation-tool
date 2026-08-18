# BMS Estimation Tool

AI-assisted analysis of HVAC Sequence of Operations (SOO) documents — extracts a control point list with source provenance, estimates labor hours, flags RFIs and exclusions, and generates a system-wise scope-of-work proposal.

Built with Claude (Anthropic API) + Streamlit.

---

## What it does

Upload a SOO PDF. The tool:

1. **Reads the document's own structure** — detects its numbered/lettered section headings and splits it into per-system chunks, rather than guessing at fixed-length blocks.
2. **Extracts control points section by section** — one request per system, so a 100+ page specification doesn't get silently truncated the way a single-call approach would.
3. **Grades every point's confidence** — high/medium/low, based on whether the equipment tag and a supporting quote actually appear verbatim in that section's source text. Not a plausibility guess.
4. **Analyzes scope, labor hours, and RFIs** in one combined pass over the full document.
5. **Generates a system-wise proposal** — each SOO system becomes a numbered scope block, grouped by equipment tag, with plain bulleted point names (matching how a controls estimator actually reads a scope section) — plus an Excel estimate, a standalone point-list workbook, and raw JSON.

---

## Architecture

Five files, no more:

| File | Role |
|---|---|
| `app.py` | Streamlit UI — the whole screen |
| `bms_analyzer_core.py` | Claude API calls: chunked extraction, combined scope/labor/RFI analysis, usage tracking |
| `soo_chunker.py` | Splits SOO text into section-aligned chunks using the document's own heading structure |
| `output_generators.py` | Word proposal, Excel estimate, point-list workbook |
| `project_store.py` | Save / load / export analyzed projects |

```
SOO PDF
  → soo_chunker.py splits by detected headings (numbered, lettered, or double-lettered)
  → bms_analyzer_core.py runs one extraction call per section (cached — a repeat run of
    the same document costs nothing)
  → each point gets a confidence grade + source section + page range + evidence quote
  → one combined call analyzes scope, labor hours, and RFIs across the whole document
  → output_generators.py turns the result into Word / Excel / JSON
```

---

## Cost controls

- **Model choice is separate for extraction vs. analysis** — extraction is transcription (bulk of the calls), analysis is judgment (one combined call). Both are selectable in the sidebar; current default is Haiku 4.5 for both.
- **Real usage tracking** — cost is computed from actual API-reported token counts, not estimated from character counts.
- **Session spend tracker** — enter your remaining balance, see it update after each run.
- **Extraction caching** — identical section text at the same model and prompt version is never re-billed.
- **Structure preview before spending anything** — page count, characters read, systems detected, and a request/cost estimate, all shown before you click Run.

---

## Demo mode

A single sidebar checkbox — **"Lock: no new API calls"** — disables the Run Analysis button entirely. Loading a previously saved or exported project still works. This exists so a live presentation never depends on a network call succeeding in the moment: analyze and validate a result beforehand, export it, then present from the export with the lock on.

---

## Projects

- **Save to session** — kept in the app's memory for the working session. Lost if the app restarts or sleeps (Streamlit Community Cloud does this automatically on inactivity).
- **Export** — a portable `.json` file. This is the only tier that actually persists. Re-open it anytime via the sidebar's "Open a project file."

---

## Setup

```bash
git clone <this-repo>
cd <this-repo>
pip install -r requirements.txt
streamlit run app.py
```

Paste an Anthropic API key in the sidebar, or set it once via Streamlit Cloud → Manage app → Settings → Secrets:

```
ANTHROPIC_API_KEY = "sk-ant-..."
```

---

## Known limitations

Being direct about this rather than letting it surface later:

- **Accuracy has not been measured against ground truth.** Coverage % (how much of the document was read) is not the same as correctness (whether the extracted points are right). A ground-truth comparison against an engineer-produced point list is planned but not yet done.
- **Heading detection is heuristic, not universal.** It has been verified against two real, structurally different SOO formats. A specification using a numbering style neither of those covers will fall back to length-based splitting, which loses per-system labeling — the app surfaces this as a warning rather than failing silently.
- **The optional controls-spec PDF upload is accepted but not yet used** in any prompt.
- **No multi-instance multiplier.** A system described once in the SOO (e.g., "typical" pump sequence) but installed multiple times on the drawings will currently produce one system's worth of points, not the installed total — cross-checking against MEP schedules is not yet implemented.

---

## Tech stack

Python · Streamlit · Anthropic API (Claude) · PyMuPDF (PDF extraction) · python-docx · openpyxl
