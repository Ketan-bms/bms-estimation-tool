"""
drawing_markup.py
─────────────────
BMS Estimation Tool — Drawing Markup Module

Pipeline:
  1. Extract schedule pages  -> build tag registry (tag -> page, coords)
  2. Extract floor plan pages -> find all tag occurrences with coordinates
  3. SOO cross-check          -> assign status per tag
  4. Generate annotated PDF   -> colored highlights per status
  5. Search                   -> find tag, return page image + page number

Status colors:
  GREEN  - in schedule + SOO confirmed + found on drawing
  AMBER  - in schedule + NO SOO sequence + found on drawing  (the wow moment)
  RED    - in schedule + NOT found on drawing
  BLUE   - found on drawing + NOT in schedule
"""

import io, re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import fitz  # PyMuPDF


COLORS = {
    "green": (0.0, 0.69, 0.31),
    "amber": (1.0, 0.75, 0.0),
    "red":   (1.0, 0.2,  0.2),
    "blue":  (0.0, 0.44, 0.75),
    "gray":  (0.6, 0.6,  0.6),
}

STATUS_LABELS = {
    "green": "SOO confirmed",
    "amber": "No SOO sequence — clarify scope",
    "red":   "Not found on drawing",
    "blue":  "On drawing, not in schedule",
}

TAG_RE = re.compile(
    r'\b((?:ASHP|DOAS|MUA|ESP|AHU|ERV|FCU|ACU|ACCU|EUH|UH|FTR|HWC|'
    r'PFHX|PCHWP|SCHWP|PHWP|SHWP|FPP|BT|GFU|AS-\d|ET-|FOP|'
    r'PFSP|SPF|HPF|GX-|EF-|HF-|TF-\d|VAV|AC-C)'
    r'[-]?[A-Z0-9][-A-Z0-9]*\d)\b',
    re.IGNORECASE
)

SCHEDULE_HEADERS = [
    "TAG", "CFM", "MOTOR HP", "VOLTAGE", "MANUFACTURER", "MODEL NUMBER",
    "DESIGNATION", "LOCATION", "CAPACITY", "AREA SERVED", "MBH",
    "SCHEDULE", "ELECTRICAL", "GPM", "EWT", "LWT", "ROWS", "FPI"
]


@dataclass
class TagOccurrence:
    tag: str
    page_no: int
    x0: float
    y0: float
    x1: float
    y1: float
    on_schedule_page: bool = False


@dataclass
class TagStatus:
    tag: str
    color: str
    in_schedule: bool
    in_soo: bool
    found_on_drawing: bool
    occurrences: list = field(default_factory=list)


class DrawingMarkup:
    def __init__(self, pdf_bytes, soo_tags=None, schedule_tags=None):
        self.pdf_bytes     = pdf_bytes
        self.soo_tags      = set(t.upper() for t in (soo_tags or set()))
        self.schedule_tags = set(t.upper() for t in (schedule_tags or set()))
        self.doc           = None
        self.schedule_pages = set()
        self.tag_occurrences = defaultdict(list)
        self.tag_statuses    = {}
        self.processed       = False

    def process(self):
        self.doc = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        self._identify_schedule_pages()
        self._extract_all_tags()
        self._assign_statuses()
        self.processed = True
        return self

    def _identify_schedule_pages(self):
        for page_idx in range(len(self.doc)):
            page = self.doc[page_idx]
            text = page.get_text().upper()
            hits = sum(1 for h in SCHEDULE_HEADERS if h.upper() in text)
            if hits >= 4:
                self.schedule_pages.add(page_idx)

    def _extract_all_tags(self):
        for page_idx in range(len(self.doc)):
            page = self.doc[page_idx]
            is_schedule = page_idx in self.schedule_pages
            text = page.get_text()
            found_tags = set(m.upper() for m in TAG_RE.findall(text))

            for tag in found_tags:
                hits = page.search_for(tag, quads=False)
                if not hits:
                    hits = page.search_for(tag.lower(), quads=False)
                if hits:
                    for rect in hits:
                        self.tag_occurrences[tag].append(TagOccurrence(
                            tag=tag, page_no=page_idx,
                            x0=rect.x0, y0=rect.y0,
                            x1=rect.x1, y1=rect.y1,
                            on_schedule_page=is_schedule,
                        ))
                else:
                    self.tag_occurrences[tag].append(TagOccurrence(
                        tag=tag, page_no=page_idx,
                        x0=0, y0=0, x1=0, y1=0,
                        on_schedule_page=is_schedule,
                    ))

    def _assign_statuses(self):
        all_found = set(self.tag_occurrences.keys())
        all_tags  = self.schedule_tags | all_found

        for tag in all_tags:
            in_sched = tag in self.schedule_tags
            in_soo   = tag in self.soo_tags
            found    = tag in all_found

            if   in_sched and in_soo and found:     color = "green"
            elif in_sched and not in_soo and found:  color = "amber"
            elif in_sched and not found:             color = "red"
            elif found and not in_sched:             color = "blue"
            else:                                    color = "gray"

            self.tag_statuses[tag] = TagStatus(
                tag=tag, color=color,
                in_schedule=in_sched, in_soo=in_soo,
                found_on_drawing=found,
                occurrences=self.tag_occurrences.get(tag, []),
            )

    # ── Search ────────────────────────────────────────────────────────────────

    def search_tag(self, query):
        if not self.processed:
            self.process()

        q = query.strip().upper()
        status = self.tag_statuses.get(q)

        if not status:
            matches = [t for t in self.tag_statuses if q in t]
            if not matches:
                return None, None, []
            q = sorted(matches)[0]
            status = self.tag_statuses[q]

        if not status.occurrences:
            return None, None, []

        # Prefer floor plan pages
        floor_occs = [o for o in status.occurrences if not o.on_schedule_page]
        occ = (floor_occs or status.occurrences)[0]
        all_pages = sorted(set(o.page_no + 1 for o in status.occurrences))

        img_bytes = self._render_page_highlighted(occ.page_no, occ, status.color)
        return img_bytes, occ.page_no + 1, all_pages

    def _render_page_highlighted(self, page_idx, occ, color_name):
        page = self.doc[page_idx]
        rgb  = COLORS.get(color_name, COLORS["gray"])

        if occ.x1 > occ.x0 and occ.y1 > occ.y0:
            rect = fitz.Rect(occ.x0 - 5, occ.y0 - 4,
                              occ.x1 + 5, occ.y1 + 4)
            # Filled highlight
            try:
                hl = page.add_highlight_annot(rect)
                hl.set_colors(stroke=rgb)
                hl.set_opacity(0.5)
                hl.update()
            except Exception:
                pass
            # Border box
            try:
                shape = page.new_shape()
                shape.draw_rect(rect)
                shape.finish(color=rgb, fill=None, width=2.0)
                shape.commit()
            except Exception:
                pass

        mat = fitz.Matrix(150/72, 150/72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")

    # ── Annotated PDF ─────────────────────────────────────────────────────────

    def generate_annotated_pdf(self):
        if not self.processed:
            self.process()

        doc_copy = fitz.open(stream=self.pdf_bytes, filetype="pdf")

        for page_idx in range(len(doc_copy)):
            page = doc_copy[page_idx]

            for tag, status in self.tag_statuses.items():
                rgb = COLORS.get(status.color, COLORS["gray"])
                for occ in status.occurrences:
                    if occ.page_no != page_idx:
                        continue
                    if occ.x1 <= occ.x0 or occ.y1 <= occ.y0:
                        continue

                    rect = fitz.Rect(occ.x0 - 3, occ.y0 - 2,
                                      occ.x1 + 3, occ.y1 + 2)
                    try:
                        hl = page.add_highlight_annot(rect)
                        hl.set_colors(stroke=rgb)
                        hl.set_opacity(0.4)
                        hl.set_info(
                            title="BMS Estimator",
                            content=f"{tag}: {STATUS_LABELS.get(status.color,'')}"
                        )
                        hl.update()
                    except Exception:
                        pass

                    try:
                        shape = page.new_shape()
                        shape.draw_rect(rect)
                        shape.finish(color=rgb, fill=None, width=1.2)
                        shape.commit()
                    except Exception:
                        pass

        self._add_summary_overlay(doc_copy)
        self._add_legend_page(doc_copy)

        out = io.BytesIO()
        doc_copy.save(out, garbage=4, deflate=True)
        doc_copy.close()
        return out.getvalue()

    def _add_summary_overlay(self, doc):
        if not doc:
            return
        page = doc[0]
        rect = page.rect
        counts = self.get_summary_counts()

        bw, bh = 200, 110
        box = fitz.Rect(rect.width-bw-12, rect.height-bh-12,
                         rect.width-12, rect.height-12)
        shape = page.new_shape()
        shape.draw_rect(box)
        shape.finish(color=(0.2,0.2,0.2), fill=(0.97,0.97,0.97),
                     width=1, fill_opacity=0.9)
        shape.commit()

        entries = [
            ("BMS Estimator — Markup Summary", (0.1,0.1,0.1), 8, True),
            (f"  {counts['green']} SOO confirmed",        COLORS["green"], 8, False),
            (f"  {counts['amber']} No SOO sequence",       COLORS["amber"], 8, False),
            (f"  {counts['red']}   Not found on drawing",  COLORS["red"],   8, False),
            (f"  {counts['blue']}  On drawing / not scheduled", COLORS["blue"], 8, False),
        ]
        y = box.y0 + 10
        for text, color, size, bold in entries:
            try:
                page.insert_text(fitz.Point(box.x0+8, y),
                                  text, fontsize=size, color=color)
            except Exception:
                pass
            y += size + 4

    def _add_legend_page(self, doc):
        page = doc.new_page(width=612, height=792)

        try:
            page.insert_text(fitz.Point(50, 60),
                              "BMS Estimation Tool — Drawing Markup Legend",
                              fontsize=16, color=(0.1,0.1,0.4))
            page.insert_text(fitz.Point(50, 80),
                              "Three-way cross-check: Schedule x SOO x Drawings",
                              fontsize=10, color=(0.5,0.5,0.5))
        except Exception:
            pass

        shape = page.new_shape()
        shape.draw_line(fitz.Point(50,92), fitz.Point(562,92))
        shape.finish(color=(0.7,0.7,0.7), width=0.5)
        shape.commit()

        entries = [
            ("green", "SOO Confirmed",
             "In schedule + SOO sequence confirmed + found on drawing. Include in scope."),
            ("amber", "No SOO Sequence — Clarify Scope",
             "In schedule + found on drawing + NO SOO sequence. Typical: EUH/UH with integral thermostats. "
             "Confirm with engineer whether BMS monitoring point is required before finalising price."),
            ("red",   "Not Found on Drawing",
             "In schedule but NOT located on the drawing set reviewed. Exclude from scope or flag."),
            ("blue",  "On Drawing — Not in Schedule",
             "Tag found on drawing but not in equipment schedule. Verify with engineer."),
        ]

        y = 110
        for color_name, label, desc in entries:
            rgb = COLORS[color_name]
            swatch = fitz.Rect(50, y, 75, y+18)
            shape = page.new_shape()
            shape.draw_rect(swatch)
            shape.finish(color=rgb, fill=rgb, width=0)
            shape.commit()
            try:
                page.insert_text(fitz.Point(82, y+13), label,
                                  fontsize=11, color=rgb)
            except Exception:
                pass

            words = desc.split()
            line, out_lines = [], []
            for w in words:
                line.append(w)
                if len(" ".join(line)) > 78:
                    out_lines.append(" ".join(line[:-1]))
                    line = [w]
            if line:
                out_lines.append(" ".join(line))

            dy = y + 26
            for ln in out_lines:
                try:
                    page.insert_text(fitz.Point(82, dy), ln,
                                      fontsize=9, color=(0.3,0.3,0.3))
                except Exception:
                    pass
                dy += 12
            y = dy + 14

        counts = self.get_summary_counts()
        y += 10
        try:
            page.insert_text(fitz.Point(50, y), "Summary",
                              fontsize=12, color=(0.1,0.1,0.4))
        except Exception:
            pass
        y += 16

        for color_name, label, _ in entries:
            rgb = COLORS[color_name]
            dot = fitz.Rect(50, y-8, 62, y+2)
            shape = page.new_shape()
            shape.draw_rect(dot)
            shape.finish(color=rgb, fill=rgb, width=0)
            shape.commit()
            try:
                page.insert_text(fitz.Point(70, y),
                                  f"{counts.get(color_name,0):3d}  {label}",
                                  fontsize=10, color=(0.2,0.2,0.2))
            except Exception:
                pass
            y += 16

        total = sum(counts.values())
        try:
            page.insert_text(fitz.Point(50, y+10),
                              f"Total unique tags processed: {total}",
                              fontsize=10, color=(0.1,0.1,0.1))
        except Exception:
            pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    def get_summary_counts(self):
        counts = {"green":0,"amber":0,"red":0,"blue":0,"gray":0}
        for s in self.tag_statuses.values():
            counts[s.color] = counts.get(s.color,0) + 1
        return counts

    def get_amber_tags(self):
        return sorted(t for t,s in self.tag_statuses.items() if s.color=="amber")

    def get_red_tags(self):
        return sorted(t for t,s in self.tag_statuses.items() if s.color=="red")

    def get_all_statuses_df(self):
        rows = []
        for tag, s in sorted(self.tag_statuses.items()):
            pages = sorted(set(o.page_no+1 for o in s.occurrences))
            rows.append({
                "Tag":          tag,
                "Status":       STATUS_LABELS.get(s.color, s.color),
                "Color":        s.color,
                "In schedule":  "✅" if s.in_schedule else "—",
                "In SOO":       "✅" if s.in_soo else ("❌" if s.in_schedule else "—"),
                "Found on dwg": "✅" if s.found_on_drawing else "❌",
                "Pages":        ", ".join(str(p) for p in pages[:6]),
            })
        return rows

    def page_count(self):
        return len(self.doc) if self.doc else 0

    def schedule_page_count(self):
        return len(self.schedule_pages)
