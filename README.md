# 🏢 BMS Estimation Tool

**AI-powered automation that turns 1 week of BMS estimation work into minutes.**

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/YOUR-USERNAME/bms-estimation-tool/main/streamlit_app_v2.py)

---

Current Status:
🚀 Phase 1: SOO Analysis
  - 8 hours → 10 minutes (98% time savings)
  - MVP in progress
  - Recognized as Company Innovation of the Month

🎯 Next: Full workflow optimization (Phase 2 in progress)

## 📊 What It Does

Upload a **Sequence of Operations (SOO) PDF** and instantly get:

✅ **Scope Analysis** - What's included/excluded from BMS scope  
✅ **Point List** - Complete DDC control points extracted from SOO  
✅ **Labor Estimation** - Hours by role (engineering, programming, installation, testing, training)  
✅ **RFIs & Exclusions** - Items needing clarification and what's out of scope  
✅ **Professional Outputs** - Word proposal + Excel estimate + JSON analysis  

---

## 🎯 The Problem It Solves

**Before:**
- Manual reading of 50+ page SOO documents
- Spreadsheets to track scope, points, labor
- 1 week per project to create proposal
- Error-prone manual process
- Inconsistent estimates

**After:**
- AI reads and analyzes SOO instantly
- Automatic point list generation
- AI estimates labor hours
- Professional outputs in minutes
- Consistent, repeatable process

**Result: 80% faster estimates** ⚡

---

## 🚀 Quick Start

### **Option 1: Use Online (No Installation)**

👉 **[Open Streamlit App](https://share.streamlit.io/YOUR-USERNAME/bms-estimation-tool/main/streamlit_app_v2.py)**

1. Paste your Anthropic API key
2. Upload your SOO PDF
3. Click "Run Analysis"
4. Download outputs

### **Option 2: Run Locally**

```bash
# Clone repo
git clone https://github.com/YOUR-USERNAME/bms-estimation-tool
cd bms-estimation-tool

# Install dependencies
pip install -r requirements.txt

# Run app
streamlit run streamlit_app_v2.py
```

Opens at: http://localhost:8501

---

## 📋 How It Works

```
SOO PDF (Input)
     ↓
PyMuPDF (Extract text)
     ↓
Claude AI (Analyze & understand)
     ↓
Generate:
  • Scope overview
  • Point list (11 columns)
  • Labor estimates (by role)
  • RFIs & exclusions
     ↓
Create Outputs:
  • Word proposal (client-ready)
  • Excel estimate (your format)
  • JSON analysis (structured data)
     ↓
User Downloads All
```

---

##🧠 AI Technology
Uses Claude AI (Anthropic) for document understanding

Model Evolution:
📊 V1: Claude Opus
  - Result: 98% accuracy on complex SOO documents
  - Trade-off: High token usage (production cost concern)
  - Learning: Works perfectly, now optimizing for scale

🚀 V2: Claude Sonnet (In Progress)
  - Goal: Maintain 98%+ accuracy with 40-50% cost reduction
  - Status: Benchmarking on real SOO documents
  - Timeline: Q3 2026

Product Thinking:
This mirrors how good products work — ship MVP with best solution,
measure real-world impact, then optimize based on actual constraints.

---

## 📁 Project Structure

```
bms-estimation-tool/
├── streamlit_app_v2.py           # Main Streamlit UI
├── bms_analyzer_core.py          # Core analysis logic (Claude integration)
├── output_generators.py          # Word & Excel output generation
├── requirements.txt              # Python dependencies
├── .streamlit/secrets.toml       # Streamlit secrets (API keys)
├── .gitignore                    # Git ignore rules
└── README.md                     # This file
```

---

## 🔧 Technology Stack

| Component | Technology |
|-----------|-----------|
| **Frontend** | Streamlit (Python web framework) |
| **AI Engine** | Claude API (Anthropic) |
| **PDF Processing** | PyMuPDF (fitz) |
| **Word Output** | python-docx |
| **Excel Output** | openpyxl |
| **Deployment** | Streamlit Cloud |
| **Version Control** | GitHub |

---

## 💻 Features

### **Analysis**
- ✅ SOO text extraction from PDF
- ✅ Automatic scope determination
- ✅ I/O point extraction
- ✅ System classification
- ✅ Integration requirement detection
- ✅ RFI identification
- ✅ Exclusion detection

### **Estimation**
- ✅ Labor hours estimation by role
- ✅ Complexity assessment
- ✅ Timeline estimation
- ✅ Risk identification
- ✅ Rate-based cost calculation

### **Output**
- ✅ Professional Word proposals
- ✅ Excel estimates (structured)
- ✅ JSON analysis (API-friendly)
- ✅ Batch download
- ✅ Customizable templates

---

## 📊 Example Output

### **Input:**
Estimation project SOO (50+ pages)

### **Instant Output:**
- **Scope:** 87 I/O points, 5 major systems (ASHP, chiller, AHU, DOAS, ERU)
- **Point List:** Panel-by-panel control points
- **Labor:** 280 hours total labor @ $38,800 cost
- **RFIs:** 3 items needing clarification
- **Proposal:** Word document ready to send to client
- **Estimate:** Excel file matching your template

**Time: 3 minutes. Manual process: 1 week.** ⚡

---

## 🔐 Security

- ✅ **No data storage** - PDFs processed but not saved
- ✅ **API key secure** - Never logged or shared
- ✅ **Open source** - Code is transparent
- ✅ **User controlled** - You keep your data

---

## 🚀 Deployment

### **Already Deployed on Streamlit Cloud**

Open the app: https://share.streamlit.io/YOUR-USERNAME/bms-estimation-tool/main/streamlit_app_v2.py

### **Deploy Your Own**

1. Fork this repo
2. Create Streamlit Cloud account
3. Connect GitHub
4. Select this repo
5. Deploy
6. Done! ✅

[Full deployment guide →](GITHUB_STREAMLIT_DEPLOYMENT.md)

---

## 📝 Usage Example

```python
from bms_analyzer_core import BMSAnalyzer
from output_generators import OutputGenerator

# Analyze SOO
analyzer = BMSAnalyzer(api_key="sk-ant-...")
results = analyzer.run_full_analysis(
    soo_pdf_path="soo.pdf",
    spec_pdf_path="spec.pdf"
)

# Generate outputs
generator = OutputGenerator()
generator.export_all_outputs(
    analysis_results=results,
    project_name="My Project",
    output_dir="./outputs"
)
```

---

## 🎯 Use Cases

✅ **BMS Estimators** - Automate proposal creation  
✅ **Controls Contractors** - Fast project scoping  
✅ **Mechanical Engineers** - Quick BMS cost estimation  
✅ **Facility Managers** - Understand controls requirements  
✅ **Sales Teams** - Faster bids  
✅ **Training** - Learn SOO analysis

---

## 📈 Performance Metrics

| Metric | Manual | Automated |
|--------|--------|-----------|
| Time per project | 1 week | 3-5 minutes |
| Manual reading | 8 hours | 1 minute |
| Point list creation | 4 hours | 1 minute |
| Labor estimation | 3 hours | 1 minute |
| Proposal writing | 2 hours | 2 minutes |
| Error rate | High | Very low |

**Speedup: 100x+ on reading phase. 80% overall time savings.** 🚀

---

## 🛣️ Roadmap

### **Phase 1 (Current)** ✅
- SOO analysis & point list
- Labor estimation
- Word + Excel output
- Streamlit deployment

### **Phase 2 (Next)**
- Quotation project tool (work-hour estimates)
- Multiple SOO handling
- Advanced labor customization
- Integration with accounting systems

### **Phase 3 (Future)**
- Floor plan OCR analysis
- Material selection automation
- Visual drawing markup
- Real-time collaboration
- SaaS pricing model

---

## 🐛 Known Limitations

- ⚠️ **SOO Format:** Works best with structured text-based SOOs (not scanned PDFs)
- ⚠️ **Floor Plans:** Not included (Phase 3)
- ⚠️ **Material Selection:** Manual for now (Phase 2)
- ⚠️ **PDF Size:** Recommend < 50MB

---

## 🤝 Contributing

Want to improve this tool?

1. Fork the repo
2. Create a feature branch
3. Make improvements
4. Submit a pull request

---

## 📞 Support & Questions

### **Issues?**
- Open a GitHub issue
- Describe the problem
- Include your SOO excerpt if possible

### **Feature Requests?**
- Check the roadmap first
- Open an issue with "Feature:" prefix
- Describe the use case

### **Questions?**
- Check README first
- Review [deployment guide](GITHUB_STREAMLIT_DEPLOYMENT.md)
- Open a discussion

---

## 📄 License

MIT License - Use freely in your projects

---

## 👤 Author

Built by Ketan - Senior BMS PM transitioning to Product Management

**Why I Built This:**
- Identified repetitive 1-week manual process
- Wanted to automate it with AI
- Built MVP to demonstrate value
- Scaling to help other teams

---


## 📊 Try It Now

👉 **[Open App](https://share.streamlit.io/YOUR-USERNAME/bms-estimation-tool/main/streamlit_app_v2.py)**

1. Get API key: https://console.anthropic.com
2. Paste key in app
3. Upload your SOO PDF
4. Click "Run Analysis"
5. Download outputs

**Takes 3 minutes. Solves a 1-week problem.** ⚡

---

**Made with ❤️ for BMS professionals and PM aspirants**
