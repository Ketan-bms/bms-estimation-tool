"""
output_generators.py - PRODUCTION MVP
Generates Word proposals and Excel estimates from analysis results
"""

import json
import os
import re
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from datetime import datetime


class OutputGenerator:
    """Generates Word proposals and Excel estimates"""
    
    def __init__(self, template_docx_path=None):
        self.template_docx_path = template_docx_path
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # ============================================================================
    # WORD PROPOSAL GENERATION
    # ============================================================================
    
    @staticmethod
    def _num(value, default=0):
        """Coerce a model-supplied value to a number.

        Claude returns JSON, but a field typed as a number in the prompt can
        still come back as "40", "$150", "40 hours", or null. Every one of
        those blows up an f-string format spec like :,.0f, so coerce here
        rather than trusting the shape.
        """
        if isinstance(value, (int, float)):
            return value
        if value is None:
            return default
        cleaned = re.sub(r"[^0-9.\-]", "", str(value))
        try:
            return float(cleaned) if cleaned not in ("", "-", ".") else default
        except ValueError:
            return default

    @staticmethod
    def _safe_table_style(table, style_name):
        """Apply a table style, falling back if the template lacks it.

        A user-supplied .docx template may not define the style, in which
        case python-docx raises KeyError and kills the whole document.
        """
        try:
            table.style = style_name
        except KeyError:
            try:
                table.style = "Table Grid"
            except KeyError:
                pass

    def generate_word_proposal(self, analysis_results, project_name, output_path):
        """Generate professional Word proposal from analysis results"""
        
        try:
            # Use template if provided, else create new
            if self.template_docx_path:
                doc = Document(self.template_docx_path)
            else:
                doc = Document()
            
            scope = analysis_results.get("scope", {})
            labor = analysis_results.get("labor_estimate", {})
            rfis = analysis_results.get("rfis", {})
            
            # ===== TITLE =====
            title = doc.add_paragraph()
            title_run = title.add_run("BMS ESTIMATION PROPOSAL")
            title_run.font.size = Pt(18)
            title_run.font.bold = True
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            # ===== PROJECT INFO =====
            doc.add_paragraph(f"Project: {project_name}")
            doc.add_paragraph(f"Date: {self.timestamp}")
            doc.add_paragraph(f"Prepared by: TEC Building Systems")
            doc.add_paragraph()
            
            # ===== SCOPE OVERVIEW =====
            doc.add_heading("SCOPE OVERVIEW", level=1)
            if scope.get("project_overview"):
                doc.add_paragraph(scope["project_overview"])
            
            # Systems in scope
            doc.add_heading("Systems in Scope", level=2)
            systems = scope.get("systems_in_scope", [])
            for system in systems:
                doc.add_paragraph(system, style='List Bullet')
            
            # ===== SCOPE CLARITY =====
            clarity = scope.get("scope_clarity", {})
            
            if clarity.get("needs_clarification"):
                doc.add_heading("Items Requiring Clarification (RFIs)", level=2)
                for item in clarity["needs_clarification"]:
                    doc.add_paragraph(item, style='List Bullet')
            
            if clarity.get("explicitly_excluded"):
                doc.add_heading("Explicitly Excluded from BMS Scope", level=2)
                for item in clarity["explicitly_excluded"]:
                    doc.add_paragraph(f"❌ {item}", style='List Bullet')
            
            # ===== LABOR ESTIMATE =====
            doc.add_heading("LABOR ESTIMATE", level=1)
            
            labor_breakdown = labor.get("labor_estimate", {})
            if labor_breakdown:
                # Create table
                table = doc.add_table(rows=1, cols=4)
                self._safe_table_style(table, 'Light Grid Accent 1')
                
                # Header row
                header_cells = table.rows[0].cells
                header_cells[0].text = "Task"
                header_cells[1].text = "Hours"
                header_cells[2].text = "Rate"
                header_cells[3].text = "Cost"
                
                # Make header bold
                for cell in header_cells:
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            run.font.bold = True
                
                # Data rows
                total_cost = 0
                for task, data in labor_breakdown.items():
                    if isinstance(data, dict):
                        row = table.add_row()
                        hours = self._num(data.get("hours"))
                        rate = self._num(data.get("rate"))
                        cost = hours * rate
                        total_cost += cost
                        
                        row.cells[0].text = task.replace("_", " ").title()
                        row.cells[1].text = str(hours)
                        row.cells[2].text = f"${rate}"
                        row.cells[3].text = f"${cost:,.0f}"
                
                # Total row
                total_row = table.add_row()
                total_cells = total_row.cells
                total_cells[0].text = "TOTAL LABOR"
                total_cells[3].text = f"${total_cost:,.0f}"
                
                # Make total bold
                for cell in total_cells:
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            run.font.bold = True
            
            # Assumptions
            if labor.get("assumptions"):
                doc.add_paragraph()
                doc.add_paragraph(f"Assumptions: {labor['assumptions']}")
            
            # ===== POINT LIST SUMMARY =====
            doc.add_heading("CONTROL POINT LIST", level=1)
            
            points = analysis_results.get("point_list", [])
            if points:
                doc.add_paragraph(f"Total Points Extracted: {len(points)}")
                
                # Create points table
                if len(points) > 0:
                    table = doc.add_table(rows=1, cols=5)
                    self._safe_table_style(table, 'Light Grid Accent 1')
                    
                    header_cells = table.rows[0].cells
                    header_cells[0].text = "Panel"
                    header_cells[1].text = "Equipment"
                    header_cells[2].text = "Point Name"
                    header_cells[3].text = "Type"
                    header_cells[4].text = "Qty"
                    
                    # Make header bold
                    for cell in header_cells:
                        for paragraph in cell.paragraphs:
                            for run in paragraph.runs:
                                run.font.bold = True
                    
                    # Show first 20 points as sample
                    for point in points[:20]:
                        row = table.add_row()
                        
                        # Determine point type
                        point_type = ""
                        if point.get("AI"):
                            point_type = "AI"
                        elif point.get("BI"):
                            point_type = "BI"
                        elif point.get("AO"):
                            point_type = "AO"
                        elif point.get("BO"):
                            point_type = "BO"
                        
                        row.cells[0].text = str(point.get("Panel", ""))
                        row.cells[1].text = str(point.get("Equipment", ""))
                        row.cells[2].text = str(point.get("Point_Name", ""))
                        row.cells[3].text = point_type
                        row.cells[4].text = str(point.get("Qty", 1))
                    
                    if len(points) > 20:
                        doc.add_paragraph(f"... and {len(points) - 20} more points (see Excel estimate for complete list)")
            
            # ===== PROJECT SUMMARY =====
            doc.add_heading("PROJECT SUMMARY", level=1)
            
            metadata = analysis_results.get("metadata", {})
            doc.add_paragraph(f"Total I/O Points: {metadata.get('total_i_o_count', 0)}")
            doc.add_paragraph(f"Total Control Points: {len(points)}")
            doc.add_paragraph(f"Estimated Labor: {self._num(labor.get('total_hours')):,.0f} hours")
            doc.add_paragraph(f"Estimated Labor Cost: ${self._num(labor.get('total_labor_cost')):,.0f}")
            
            # ===== NEXT STEPS =====
            doc.add_heading("Next Steps", level=2)
            doc.add_paragraph("1. Review this proposal for accuracy")
            doc.add_paragraph("2. Address RFIs if any items need clarification")
            doc.add_paragraph("3. Confirm exclusions with design team")
            doc.add_paragraph("4. Schedule kickoff meeting")
            
            # Save document
            doc.save(output_path)
            return True
            
        except Exception as e:
            # Do not swallow. print() goes to the server console where the
            # user never sees it, and the caller then tries to open a file
            # that was never written.
            raise RuntimeError("Word proposal generation failed: %s" % e) from e
    
    # ============================================================================
    # EXCEL ESTIMATE GENERATION
    # ============================================================================
    
    def generate_excel_estimate(self, analysis_results, project_name, output_path):
        """Generate Excel estimate matching your template structure"""
        
        try:
            wb = openpyxl.Workbook()
            
            # ===== SUMMARY SHEET =====
            ws_summary = wb.active
            ws_summary.title = "Summary"
            
            # Header
            ws_summary['A1'] = "General Project Information"
            ws_summary['B1'] = "Region:"
            ws_summary['C1'] = "New York"
            
            ws_summary['A2'] = "Project Name"
            ws_summary['C2'] = project_name
            
            ws_summary['A3'] = "Date"
            ws_summary['C3'] = self.timestamp
            
            # Material Summary
            ws_summary['A8'] = "Material Summary"
            ws_summary['A9'] = "Material cost:"
            ws_summary['A10'] = "Tax"
            ws_summary['A11'] = "Misc"
            ws_summary['A12'] = "Shipping"
            ws_summary['A13'] = "Warranty"
            
            labor = analysis_results.get("labor_estimate", {})
            ws_summary['A15'] = "Labor Summary"
            ws_summary['A16'] = "Total Labor Hours"
            ws_summary['C16'] = self._num(labor.get("total_hours"))
            ws_summary['A17'] = "Total Labor Cost"
            ws_summary['C17'] = self._num(labor.get("total_labor_cost"))
            
            # Format as currency
            for row in [9, 10, 11, 12, 13, 17]:
                ws_summary[f'C{row}'].number_format = '$#,##0.00'
            
            # ===== POINTS LIST SHEET =====
            ws_points = wb.create_sheet("Points List")
            
            # Headers
            # Field order matches the 11-column working format, with the
            # audit-trail columns appended so every row can be traced back
            # to the section and wording it came from.
            headers = [
                ("Panel", "Panel"),
                ("Equipment", "Equipment"),
                ("Point_Name", "Point_Name"),
                ("Control Device", "Control Device"),
                ("AI", "AI"), ("BI", "BI"), ("AO", "AO"), ("BO", "BO"),
                ("Qty", "Qty"),
                ("Description", "Description"),
                ("Confidence", "Confidence"),
                ("Source_Section", "Source Section"),
                ("Source_Pages", "SOO Pages"),
                ("Evidence", "Evidence (verbatim)"),
                ("Repeats_In_Sections", "Repeats"),
            ]
            for col_idx, (_, label) in enumerate(headers, 1):
                cell = ws_points.cell(1, col_idx)
                cell.value = label
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="D3D3D3", end_color="D3D3D3", fill_type="solid")

            points = analysis_results.get("point_list", [])
            conf_fill = {
                "high": PatternFill(start_color="E6F4EA", end_color="E6F4EA", fill_type="solid"),
                "medium": PatternFill(start_color="FFF7E0", end_color="FFF7E0", fill_type="solid"),
                "low": PatternFill(start_color="FCE8E6", end_color="FCE8E6", fill_type="solid"),
            }

            for row_idx, point in enumerate(points, 2):
                for col_idx, (key, _) in enumerate(headers, 1):
                    ws_points.cell(row_idx, col_idx).value = point.get(key, "")
                # Shade the confidence cell so low-confidence rows are
                # obvious when the sheet is reviewed by hand.
                fill = conf_fill.get(str(point.get("Confidence", "")).lower())
                if fill:
                    ws_points.cell(row_idx, 11).fill = fill

            ws_points.freeze_panes = "A2"
            
            # Adjust column widths
            for col, width in (("K", 12), ("L", 42), ("M", 11), ("N", 46), ("O", 9)):
                ws_points.column_dimensions[col].width = width
            ws_points.column_dimensions['A'].width = 12
            ws_points.column_dimensions['B'].width = 12
            ws_points.column_dimensions['C'].width = 25
            ws_points.column_dimensions['D'].width = 15
            
            # ===== LABOR BREAKDOWN SHEET =====
            ws_labor = wb.create_sheet("Labor Estimate")
            
            ws_labor['A1'] = "Labor Breakdown"
            ws_labor['A2'] = "Task"
            ws_labor['B2'] = "Hours"
            ws_labor['C2'] = "Rate/hr"
            ws_labor['D2'] = "Total"
            
            labor_breakdown = labor.get("labor_estimate", {})
            row = 3
            total_cost = 0
            
            for task, data in labor_breakdown.items():
                if isinstance(data, dict):
                    hours = self._num(data.get("hours"))
                    rate = self._num(data.get("rate"))
                    cost = hours * rate
                    total_cost += cost
                    
                    ws_labor[f'A{row}'] = task.replace("_", " ").title()
                    ws_labor[f'B{row}'] = hours
                    ws_labor[f'C{row}'] = rate
                    ws_labor[f'D{row}'] = cost
                    ws_labor[f'D{row}'].number_format = '$#,##0.00'
                    row += 1
            
            # Total row
            ws_labor[f'A{row}'] = "TOTAL"
            ws_labor[f'D{row}'] = total_cost
            ws_labor[f'D{row}'].number_format = '$#,##0.00'
            ws_labor[f'A{row}'].font = Font(bold=True)
            ws_labor[f'D{row}'].font = Font(bold=True)
            
            # ===== ANALYSIS NOTES SHEET =====
            ws_notes = wb.create_sheet("Analysis Notes")
            
            ws_notes['A1'] = "Scope Analysis Notes"
            scope = analysis_results.get("scope", {})
            ws_notes['A3'] = "Systems in Scope:"
            row = 4
            for system in scope.get("systems_in_scope", []):
                ws_notes[f'A{row}'] = system
                row += 1
            
            rfis = analysis_results.get("rfis", {})
            ws_notes['A10'] = "RFIs (Items needing clarification):"
            row = 11
            for rfi in rfis.get("rfis", []):
                ws_notes[f'A{row}'] = rfi
                row += 1
            
            ws_notes['A20'] = "Exclusions:"
            row = 21
            for exc in rfis.get("exclusions", []):
                ws_notes[f'A{row}'] = exc
                row += 1
            
            # Column widths
            ws_notes.column_dimensions['A'].width = 60
            
            # Save workbook
            wb.save(output_path)
            return True
            
        except Exception as e:
            raise RuntimeError("Excel estimate generation failed: %s" % e) from e
    
    # ============================================================================
    # BULK EXPORT
    # ============================================================================
    
    def export_all_outputs(self, analysis_results, project_name, output_dir):
        """Generate all output files at once"""
        
        word_path = f"{output_dir}/{project_name}_Proposal.docx"
        excel_path = f"{output_dir}/{project_name}_Estimate.xlsx"
        
        self.generate_word_proposal(analysis_results, project_name, word_path)
        self.generate_excel_estimate(analysis_results, project_name, excel_path)

        outputs = {}
        if os.path.exists(word_path):
            outputs["proposal"] = word_path
        if os.path.exists(excel_path):
            outputs["estimate"] = excel_path
        return outputs


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    # Load analysis results from JSON
    with open("analysis_results.json", "r") as f:
        results = json.load(f)
    
    # Generate outputs
    generator = OutputGenerator(template_docx_path="175_Park_Avenue_Proposal.docx")
    
    generator.export_all_outputs(
        analysis_results=results,
        project_name="175_Park_Avenue",
        output_dir="./outputs"
    )
