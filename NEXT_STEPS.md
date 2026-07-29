# BMS Estimation Tool — SOO Reader & Point List Integration

## ✅ What Was Done

### 1. **New Point List Extractor Module** (`point_list_extractor.py`)
- **`generate_point_list_prompt()`**: Creates a Claude prompt to extract points from SOO with BMS-specific columns
- **`parse_point_list_response()`**: Parses Claude's JSON response and applies I/O type inference
- **`infer_io_type()`**: Automatically detects I/O type (AI, BI, AO, BO, Serial_Pt) from point name and description

### 2. **Updated app.py**
- **Imports**: Added `from point_list_extractor import ...`
- **`ai_point_list()` function**: Replaced old generic implementation with new BMS-specific version
  - Now uses: Panel Name · Equipment · Point Name · Control Device · AI · BI · AO · BO · Serial_Pt · Terms · Remarks
  - No longer uses: System/Device, Tag, Qty columns
  - Uses 'x' instead of '1' for I/O columns
- **`module_point_list()` UI**: 
  - Better diagnostics showing SOO load status and file size
  - Clearer error messages for missing API key
  - Visual confirmation when SOO is loaded
  - Shows point count in dashboard
- **Data editor**: Updated to show new BMS columns in order

### 3. **Test Files**
- **`test_soo_extraction.py`**: Tests SOO text reading and I/O type inference
- **`test_integration.py`**: Full end-to-end test simulating Claude response → point list

---

## 🚀 How to Test

### Option A: Local Testing (Before Deploying)

```bash
# Test SOO extraction and I/O inference
python test_soo_extraction.py

# Test full integration (parsing Claude responses)
python test_integration.py
```

Both tests should show ✅ for all checks.

---

### Option B: Live Testing in Streamlit (After Deploy)

1. **Deploy to Streamlit Cloud**
   ```bash
   git add -A
   git commit -m "feat: new BMS-specific point list columns + SOO reader"
   git push origin main
   ```

2. **Open the Streamlit app** at your Streamlit Cloud URL

3. **Test the Point List module:**
   - Go to **Point List** tab
   - Upload a test SOO (West 34th Street Hotel SOO recommended)
   - Verify "SOO loaded" status shows ✅
   - Click **"🤖 Generate point list"**
   - Wait for extraction (~15–30 seconds)
   - Should see rows like:
     ```
     Panel Name    Equipment   Point Name                  AI  BO  Terms
     MER-DDC-1     ASHP-1      Compressor Enable                x   OUT-1
     MER-DDC-1     ASHP-1      Leaving Water Temperature   x        AI-1
     ```

4. **Test the data editor:**
   - Edit any cell (e.g., Panel Name, Terms)
   - Changes save automatically to session state
   - Refresh browser → data persists

5. **Export to Excel:**
   - Click **"⬇ Export to Excel"**
   - Download should have all 11 columns

---

## 📋 Column Reference

| Column       | Purpose                          | Example                  | Notes               |
|--------------|----------------------------------|--------------------------|---------------------|
| Panel Name   | Control panel identifier         | MER-DDC-1, AHU-1-CTL    | Inferred from equipment |
| Equipment    | Device/system tag                | ASHP-1, DOAS-1M-1       | From SOO            |
| Point Name   | Exact point description          | Supply Fan Start/Stop   | From SOO            |
| Control Device | Controller type                | Honeywell PLC           | From SOO or inferred |
| AI           | Analog Input                     | x or empty              | Auto-detected       |
| BI           | Binary Input (status, alarm)     | x or empty              | Auto-detected       |
| AO           | Analog Output (modulation)       | x or empty              | Auto-detected       |
| BO           | Binary Output (start/stop)       | x or empty              | Auto-detected       |
| Serial_Pt    | BACnet/network point            | x or empty              | Auto-detected       |
| Terms        | Terminal designations            | OUT-1, IN-2             | From SOO            |
| Remarks      | Operational notes                | "Energize to enable"    | From SOO            |

---

## 🧠 I/O Type Inference Rules

Claude extracts all fields; Python then auto-detects I/O type using keyword patterns:

### Binary Output (BO)
- Keywords: start, stop, enable, disable, open, close, valve control, damper control, command, signal

### Binary Input (BI)
- Keywords: status, alarm, fault, indication, feedback, end switch, limit, safety

### Analog Output (AO)
- Keywords: modulation, speed control, position, setpoint, 0-10V, 4-20mA

### Analog Input (AI)
- Keywords: temperature, humidity, pressure, flow, sensor, reading, dry bulb, dew point

### Serial (Serial_Pt)
- Keywords: BACnet, Modbus, network, communication, interface

**Default**: If no keywords match → AI (assumes sensor reading)

---

## 🔍 Troubleshooting

### Issue: "Parse failed — check API key"
**Solution:** 
- Verify `ANTHROPIC_API_KEY` is set in Streamlit Secrets
- Check that key starts with `sk-ant-` (not `sk-proj-`)
- Test key in terminal: `echo $ANTHROPIC_API_KEY`

### Issue: "No SOO found"
**Solution:**
- Verify SOO PDF is uploaded in Takeoff tab
- Check file size in diagnostics (should be > 10 KB)
- Try uploading again

### Issue: Empty rows returned
**Solution:**
- This means Claude parsed the response but found no points
- SOO may be too short or in unexpected format
- Add more sample SOO text (at least 2000 chars)
- Manually add a few rows and edit in the data editor

### Issue: I/O types not inferred
**Solution:**
- Click **"🤖 Generate point list"** again
- The infer_io_type() function runs automatically after Claude extraction
- Check that Point Name contains keywords (e.g., "temperature", "status", "control")

---

## 📝 Next Steps (After Testing)

1. **Test with real West 34th Street Hotel SOO**
   - Upload SOO PDF in Takeoff tab
   - Generate point list
   - Verify 60+ points extracted with proper I/O types
   - Check for unit heaters (EUH) — should appear as BO (start/stop) and AI (temperature)

2. **Refine Panel Name logic** (if needed)
   - Currently inferred from Equipment prefix (e.g., "MER-DDC-1" → "MER")
   - Can be improved if you have specific panel assignments

3. **Add custom I/O keyword mappings** (if needed)
   - Edit `infer_io_type()` function in `point_list_extractor.py`
   - Add project-specific or manufacturer-specific keywords

4. **Client template support**
   - If you have a custom point list template, add it in Clients tab
   - Column names in template will override defaults

---

## 📌 Files Changed/Created

```
Created:
  ├── point_list_extractor.py        ← New BMS point list module
  ├── test_soo_extraction.py         ← Test SOO reader
  ├── test_integration.py             ← Full integration test
  └── NEXT_STEPS.md                   ← This file

Modified:
  └── app.py
      ├── Import point_list_extractor
      ├── Replace ai_point_list() function
      ├── Update module_point_list() UI
      └── Update data editor columns
```

---

## 🎯 Key Features

✅ **AI extracts all columns from SOO** — more automated  
✅ **I/O types auto-inferred** — pattern matching on point names  
✅ **'x' notation** — cleaner than '1' for binary flags  
✅ **No Qty column** — one row per point instance  
✅ **User editable** — all cells can be refined in data editor  
✅ **Export to Excel** — preserves formatting and client templates  

---

## 🧪 Example Output

When you run the integration test, you'll see:

```
1. ASHP-1       | Compressor Enable                   | BO=x
   Terms: OUT-1

2. ASHP-1       | Compressor Run Status               | BI=x
   Terms: IN-1

3. ASHP-1       | Leaving Water Temperature           | AI=x | AO=x
   Terms: AI-1
```

This shows:
- Point 1: Binary output (command to turn on compressor)
- Point 2: Binary input (feedback that compressor is running)
- Point 3: Analog input (temperature reading) + Analog output (in case of proportional coil)

---

## Questions?

If you run into issues:
1. Check diagnostics panel (expand "🔍 Diagnostics & SOO Preview")
2. Verify API key in Streamlit Secrets
3. Try the test scripts: `python test_integration.py`
4. Check app logs for detailed error messages
