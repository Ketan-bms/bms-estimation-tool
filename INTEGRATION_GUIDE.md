# How to Add SOO Extraction to app.py (5 Buttons)

## Step 1: Copy Files to Your Project

```bash
# Copy the extraction modules
cp soo_extractor.py controls_spec_extractor.py soo_module_ui.py /your/project/path/
```

## Step 2: Update app.py Imports

**Find this section (line ~7-11):**
```python
import json, os, io, base64
from material_module import module_material, init_pricebooks
from markup_ui import module_markup
from pdf_takeoff import run_pdf_takeoff, takeoff_to_session_format
from point_list_extractor import generate_point_list_prompt, parse_point_list_response, infer_io_type
from pathlib import Path
from datetime import date
from collections import defaultdict
```

**Add these imports:**
```python
import json, os, io, base64
from material_module import module_material, init_pricebooks
from markup_ui import module_markup
from pdf_takeoff import run_pdf_takeoff, takeoff_to_session_format
from point_list_extractor import generate_point_list_prompt, parse_point_list_response, infer_io_type
from soo_module_ui import module_soo  # ← ADD THIS LINE
from soo_extractor import (  # ← ADD THESE LINES
    generate_overview_prompt,
    generate_pointlist_prompt,
    generate_appendix_prompt,
    generate_important_notes_prompt,
    parse_pointlist_response,
    parse_notes_response
)
from controls_spec_extractor import (  # ← ADD THESE LINES
    generate_notes_prompt,
    generate_questions_prompt,
    parse_questions_response
)
from pathlib import Path
from datetime import date
from collections import defaultdict
```

## Step 3: Add SOO Tab to Main Navigation

**Find where tabs are defined (around line 1230):**
```python
handlers = [module_takeoff, module_point_list, module_estimate,
            module_proposal, module_material, module_markup]
```

**Replace the handlers section with:**
```python
# Include SOO at the beginning
handlers = [module_soo, module_takeoff, module_point_list, module_estimate,
            module_proposal, module_material, module_markup]

# Update MODULE_ORDER (line ~36)
MODULE_ORDER = ["SOO", "Takeoff", "Point List", "Estimate", "Proposal"]
```

## Step 4: Check Your Streamlit Secrets

**Ensure `ANTHROPIC_API_KEY` is set:**

In your Streamlit Cloud dashboard → Settings → Secrets, add:
```
ANTHROPIC_API_KEY = "sk-ant-YOUR_KEY_HERE"
```

Or locally, create `.streamlit/secrets.toml`:
```toml
ANTHROPIC_API_KEY = "sk-ant-YOUR_KEY_HERE"
```

## Step 5: Test Locally

```bash
streamlit run app.py
```

You should see:
1. New "SOO" tab at the top
2. File uploader for SOO PDF/DOCX
3. **5 extraction buttons:**
   - 📋 Overview
   - 📄 Proposal
   - 📊 Point List
   - 📎 Appendix
   - ⭐ Notes

## Step 6: Deploy to Streamlit Cloud

```bash
git add soo_extractor.py controls_spec_extractor.py soo_module_ui.py app.py
git commit -m "feat: Add SOO extraction with 5 workflows (Overview, Proposal, Point List, Appendix, Notes)"
git push origin main
```

Streamlit Cloud redeploys automatically.

---

## Troubleshooting

### "No module named soo_extractor"
- Make sure files are in same directory as app.py
- Check file names are exact (lowercase, no spaces)

### "ModuleNotFoundError: No module named 'anthropic'"
- Install: `pip install anthropic`

### "No API key"
- Add ANTHROPIC_API_KEY to Streamlit Secrets
- Key must start with `sk-ant-`

### Buttons don't work
- Check API key is valid
- Check SOO text was extracted (green checkmark)
- Check Claude response (may see error in sidebar logs)

### "Parse error"
- Claude response may be malformed JSON
- Try again with better SOO text (2000+ characters)
- Check console/sidebar for detailed error

---

## What Each Button Does

### 📋 Overview
- Analyzes SOO to extract bird's eye view
- Shows system breakdown, control approach, integration method
- NO quantities (just control strategy)
- Output: Table/JSON display

### 📄 Proposal
- Requires your proposal template (DOCX)
- Generates new DOCX following your format
- Maintains "Qty x" notation
- Output: Text preview + download option

### 📊 Point List
- Extracts ALL BMS points from SOO
- Uses your 11-column format:
  - Panel Name, Equipment, Point name, Control Device
  - AI, BI, AO, BO, Serial Pt, Terms, Remarks
- System-wise organization
- Output: Table + Excel download

### 📎 Appendix
- Extracts ONLY special sequences NOT in main list
- Fire safety, emergency pressurization, future expansion
- Same 11-column format
- Output: Table + Excel download

### ⭐ Notes
- Extracts key estimation points (7 categories):
  - DDC complexity & wiring
  - Special integrations
  - Control sequences
  - Safety & interlocks
  - Commissioning requirements
  - Lead times
  - Client requirements
- Output: Organized list display

---

## Example Workflow

1. **Open SOO Tab**
2. **Upload SOO PDF** → Green checkmark appears
3. **Click "📋 Overview"** → See system breakdown
4. **Click "📊 Point List"** → See 100+ BMS points extracted
5. **Click "⭐ Notes"** → See estimation notes
6. **Click "📥 Download"** → Get Excel file with all points

---

## If Still Not Working

**Check these in order:**

1. ✅ SOO file uploaded (green checkmark visible)
2. ✅ API key set (no error message about API key)
3. ✅ All module files copied to project directory
4. ✅ Imports added to app.py
5. ✅ `module_soo` added to handlers list
6. ✅ Try clicking "📋 Overview" first (simplest extraction)
7. ✅ Check Streamlit sidebar logs for detailed error

If error persists:
- Run `streamlit run app.py --logger.level=debug`
- Look for actual error message
- Share error details with me

---

## Quick File Checklist

```
Your project directory should have:
✅ app.py (updated with imports + module_soo call)
✅ soo_extractor.py (280 lines)
✅ controls_spec_extractor.py (250 lines)
✅ soo_module_ui.py (400 lines)
✅ point_list_extractor.py (already exists)
✅ proposal_generator_module.py (already exists)
✅ All other existing files (unchanged)

.streamlit/secrets.toml:
✅ ANTHROPIC_API_KEY = "sk-ant-..."
```

---

**Ready? Follow these steps and the 5 buttons will appear!** 🚀
