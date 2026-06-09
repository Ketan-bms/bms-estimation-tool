"""
markup_ui.py
────────────
Streamlit UI for the Drawing Markup module.
Called as module_markup(p) inside the project detail page.

Adds a new "Drawing Markup" tab to the project with:
  - Document processing pipeline with progress
  - Search bar (tag search → page preview)
  - Status table (all tags with color/status)
  - Annotated PDF download
  - Proposal auto-fill for Clarifications + Exclusions
"""

import io
import streamlit as st
from drawing_markup import DrawingMarkup, STATUS_LABELS, COLORS


STATUS_EMOJI = {
    "green": "🟢",
    "amber": "🟡",
    "red":   "🔴",
    "blue":  "🔵",
    "gray":  "⚪",
}

STATUS_COLOR_CSS = {
    "green": "background-color:#e6f4ea;color:#1e4620",
    "amber": "background-color:#fff8e1;color:#7c4b00",
    "red":   "background-color:#fce8e6;color:#7c1f1a",
    "blue":  "background-color:#e8f0fe;color:#1a3a6b",
    "gray":  "background-color:#f5f5f5;color:#555",
}


def module_markup(p):
    st.markdown("### Drawing markup")
    st.caption(
        "Upload your drawing set once — tool finds schedule pages, "
        "cross-checks SOO, then highlights every device tag by status. "
        "Search any tag to jump straight to its page."
    )

    # ── Document status ───────────────────────────────────────────────────────
    docs = p.get("doc_names", {})
    has_drawings = "Drawings" in docs

    c1, c2, c3 = st.columns(3)
    c1.info(f"📐 Drawings: `{docs.get('Drawings', 'not uploaded')}`")
    c2.info(f"📄 SOO: `{docs.get('SOO', 'not uploaded')}`")
    c3.info(f"📋 Takeoff: {len(p['takeoff'].get('equipment', []))} devices loaded")

    if not has_drawings:
        st.warning("Upload drawings in the Takeoff tab first.")
        return

    # ── Build/cache the DrawingMarkup object in session state ─────────────────
    cache_key = f"dm_{p['name']}"
    dm_cached  = st.session_state.get(cache_key)
    already_processed = dm_cached is not None and dm_cached.processed

    if not already_processed:
        if st.button("🔍 Process drawings & run markup", type="primary",
                     key="run_markup"):
            _run_processing(p, cache_key)
            st.rerun()
        st.info("Click to process. This reads every page, finds all device tags, "
                "and cross-checks against SOO. Takes ~5-15 seconds for a 15MB set.")
        return

    dm: DrawingMarkup = st.session_state[cache_key]

    # ── Top stats ─────────────────────────────────────────────────────────────
    counts = dm.get_summary_counts()
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Pages",          dm.page_count())
    m2.metric("Schedule pages", dm.schedule_page_count())
    m3.metric("🟢 Confirmed",   counts["green"])
    m4.metric("🟡 Amber",       counts["amber"],
              delta="clarify scope" if counts["amber"] else None,
              delta_color="inverse" if counts["amber"] else "normal")
    m5.metric("🔴 Not found",   counts["red"])

    # Amber banner — the wow moment
    amber_tags = dm.get_amber_tags()
    if amber_tags:
        st.markdown(
            f'<div style="background:#fff3cd;border-left:4px solid #ffc000;'
            f'padding:10px 16px;border-radius:0 6px 6px 0;margin:8px 0">'
            f'⚠️ <strong>{len(amber_tags)} devices have no SOO sequence</strong> — '
            f'{", ".join(amber_tags[:8])}{"…" if len(amber_tags) > 8 else ""}. '
            f'These appear in the schedule and on the drawing but have no BMS control sequence. '
            f'Confirm scope with engineer before pricing.</div>',
            unsafe_allow_html=True
        )

    st.divider()

    # ── Main content: two tabs ────────────────────────────────────────────────
    tab_search, tab_table, tab_export = st.tabs(
        ["🔍 Search & preview", "📋 All tags", "⬇ Export"]
    )

    # ── TAB 1: Search & preview ───────────────────────────────────────────────
    with tab_search:
        st.markdown("**Search for a device tag**")
        st.caption("Type a tag or partial tag — tool jumps to the page and highlights it.")

        sc1, sc2 = st.columns([2, 1])
        query = sc1.text_input(
            "Tag search", placeholder="UH-SC-1, FCU, EUH…",
            key="markup_search", label_visibility="collapsed"
        )
        search_clicked = sc2.button("Find on drawing ↗", type="primary",
                                     key="markup_find")

        if query and (search_clicked or len(query) >= 5):
            img_bytes, page_no, all_pages = dm.search_tag(query)

            if img_bytes is None:
                st.error(f"Tag `{query.upper()}` not found in this drawing set.")
            else:
                tag_upper = query.strip().upper()
                status = dm.tag_statuses.get(tag_upper)

                # If partial match, get the resolved tag
                if not status:
                    matches = [t for t in dm.tag_statuses if tag_upper in t]
                    if matches:
                        tag_upper = sorted(matches)[0]
                        status = dm.tag_statuses[tag_upper]

                if status:
                    color = status.color
                    emoji = STATUS_EMOJI.get(color, "⚪")
                    label = STATUS_LABELS.get(color, color)
                    css   = STATUS_COLOR_CSS.get(color, "")
                    st.markdown(
                        f'<div style="{css};padding:8px 14px;border-radius:6px;'
                        f'margin-bottom:8px;font-size:13px">'
                        f'{emoji} <strong>{tag_upper}</strong> — {label} &nbsp;·&nbsp; '
                        f'Found on page{"s" if len(all_pages)>1 else ""}: '
                        f'{", ".join(str(p) for p in all_pages)}</div>',
                        unsafe_allow_html=True
                    )

                    # Show action guidance
                    if color == "amber":
                        st.warning(
                            f"⚠️ **Action required:** {tag_upper} is on the drawing "
                            f"but has no SOO sequence. Ask the engineer: "
                            f"*'Is BMS monitoring required for this device?'* "
                            f"Add to Clarifications in the proposal."
                        )
                    elif color == "red":
                        st.error(
                            f"🔴 **Not found on drawing.** {tag_upper} is in the schedule "
                            f"but was not located in this drawing set. "
                            f"Check if it's on a separate drawing. Add to Exclusions if not found."
                        )
                    elif color == "blue":
                        st.info(
                            f"🔵 {tag_upper} was found on the drawing but is not in the "
                            f"equipment schedule. Verify with engineer — may be an addition to scope."
                        )

                # Page image
                st.markdown(f"**Page {page_no}**")
                st.image(img_bytes, use_container_width=True,
                         caption=f"{tag_upper} highlighted on page {page_no}")

                # Jump to other pages
                if len(all_pages) > 1:
                    st.caption(f"Also appears on pages: {', '.join(str(p) for p in all_pages)}")
                    jump_page = st.selectbox(
                        "View on page", all_pages,
                        index=0, key="markup_page_jump"
                    )
                    if jump_page != page_no:
                        # Find occurrence on that page
                        status2 = dm.tag_statuses.get(tag_upper)
                        if status2:
                            occ2 = next(
                                (o for o in status2.occurrences
                                 if o.page_no == jump_page - 1), None
                            )
                            if occ2:
                                img2 = dm._render_page_highlighted(
                                    occ2.page_no, occ2, status2.color
                                )
                                st.image(img2, use_container_width=True,
                                         caption=f"{tag_upper} on page {jump_page}")

    # ── TAB 2: All tags table ─────────────────────────────────────────────────
    with tab_table:
        rows = dm.get_all_statuses_df()

        # Filters
        f1, f2, f3 = st.columns([2, 1.5, 1.5])
        tbl_search = f1.text_input("Filter tags", placeholder="Search…",
                                    key="tbl_search")
        status_filter = f2.selectbox("Status filter", [
            "All", "🟢 SOO confirmed", "🟡 No SOO sequence",
            "🔴 Not found", "🔵 Not in schedule"
        ], key="tbl_status_filter")
        sort_by = f3.selectbox("Sort by", ["Tag", "Status", "Pages"],
                                key="tbl_sort")

        status_map = {
            "🟢 SOO confirmed":    "SOO confirmed",
            "🟡 No SOO sequence":  "No SOO sequence — clarify scope",
            "🔴 Not found":        "Not found on drawing",
            "🔵 Not in schedule":  "On drawing, not in schedule",
        }

        filtered = rows
        if tbl_search:
            sl = tbl_search.lower()
            filtered = [r for r in filtered if sl in r["Tag"].lower()]
        if status_filter != "All":
            target = status_map.get(status_filter, "")
            filtered = [r for r in filtered if r["Status"] == target]
        if sort_by == "Status":
            order = {"amber":0,"red":1,"blue":2,"green":3,"gray":4}
            filtered = sorted(filtered, key=lambda r: order.get(r["Color"],5))
        elif sort_by == "Pages":
            filtered = sorted(filtered, key=lambda r: r["Pages"])

        st.markdown(f"**{len(filtered)} tags**")

        import pandas as pd

        def highlight_row(row):
            css = STATUS_COLOR_CSS.get(row["Color"], "")
            return [css] * len(row)

        df = pd.DataFrame(
            [{k: v for k, v in r.items() if k != "Color"} for r in filtered]
        )
        color_col = [r["Color"] for r in filtered]

        if not df.empty:
            df_display = df.copy()
            df_display.insert(0, "_color", color_col)

            styled = df_display.style.apply(
                lambda row: [STATUS_COLOR_CSS.get(row["_color"],"")] * len(row),
                axis=1
            ).hide(axis="columns", subset=["_color"])

            st.dataframe(styled, use_container_width=True,
                         hide_index=True, height=450)
        else:
            st.info("No tags match your filter.")

        # Quick action: add amber tags to proposal
        if amber_tags and st.button(
            "📝 Send amber tags to proposal Clarifications", key="send_amber"
        ):
            _push_to_proposal(p, dm)
            st.success("✅ Clarifications and Exclusions added to proposal. "
                       "Open the Proposal tab to review.")

    # ── TAB 3: Export ─────────────────────────────────────────────────────────
    with tab_export:
        st.markdown("**Annotated PDF**")
        st.caption(
            "Generates the full drawing set with colored highlights baked in. "
            "Opens in any PDF viewer. Includes a legend page at the end."
        )

        col_gen, col_info = st.columns([1, 2])

        if col_gen.button("Generate annotated PDF", type="primary",
                           key="gen_pdf"):
            with st.spinner("Building annotated PDF — drawing highlights on every page…"):
                pdf_bytes = dm.generate_annotated_pdf()
            st.session_state[f"annotated_pdf_{p['name']}"] = pdf_bytes
            st.success(f"✅ PDF ready — {len(pdf_bytes)//1024} KB")

        cached_pdf = st.session_state.get(f"annotated_pdf_{p['name']}")
        if cached_pdf:
            st.download_button(
                "⬇ Download annotated PDF",
                data=cached_pdf,
                file_name=f"markup_{p['name'].replace(' ','_')}.pdf",
                mime="application/pdf",
                key="dl_annotated"
            )

        col_info.markdown("""
**Color legend:**
- 🟢 **Green** — SOO confirmed + found on drawing
- 🟡 **Amber** — No SOO sequence (clarify with engineer)
- 🔴 **Red** — In schedule, not found on drawing
- 🔵 **Blue** — On drawing, not in schedule

**Legend page** is appended at the end of the PDF.
**Summary box** appears on page 1 with counts per status.
        """)

        st.divider()
        st.markdown("**Re-process drawings**")
        st.caption("Use this if you uploaded new documents or the SOO has changed.")
        if st.button("🔄 Re-process", key="reprocess_markup"):
            if cache_key in st.session_state:
                del st.session_state[cache_key]
            st.rerun()


# ── Processing helper ─────────────────────────────────────────────────────────

def _run_processing(p, cache_key):
    pdf_bytes = p["docs"].get("Drawings")
    if not pdf_bytes:
        st.error("Drawings not uploaded.")
        return

    # Build tag sets from existing project data
    equip = p["takeoff"].get("equipment", [])
    schedule_tags = set(e.get("tag","").upper() for e in equip if e.get("tag"))

    # SOO confirmed tags
    soo_tags = set(
        e.get("tag","").upper()
        for e in equip
        if e.get("soo_confirmed") is True
    )

    # Also add SOO tags from soo_refs if available
    # (these would be in session state if loaded)

    progress = st.progress(0, text="Opening PDF…")
    dm = DrawingMarkup(pdf_bytes, soo_tags=soo_tags, schedule_tags=schedule_tags)

    progress.progress(20, text="Identifying schedule pages…")
    dm.doc = __import__("fitz").open(stream=pdf_bytes, filetype="pdf")
    dm._identify_schedule_pages()

    progress.progress(40, text=f"Found {len(dm.schedule_pages)} schedule pages. Extracting tags…")
    dm._extract_all_tags()

    progress.progress(75, text="Running SOO cross-check…")
    dm._assign_statuses()
    dm.processed = True

    progress.progress(100, text="Done.")
    st.session_state[cache_key] = dm

    counts = dm.get_summary_counts()
    st.success(
        f"✅ Processed {dm.page_count()} pages · "
        f"{dm.schedule_page_count()} schedule pages · "
        f"{counts['green']} confirmed · "
        f"{counts['amber']} amber · "
        f"{counts['red']} not found"
    )


# ── Push amber/red to proposal ────────────────────────────────────────────────

def _push_to_proposal(p, dm):
    amber = dm.get_amber_tags()
    red   = dm.get_red_tags()

    existing = p["proposal"].get("text", "")

    clarifications = ""
    if amber:
        clarifications = (
            "\n\nCLARIFICATIONS:\n"
            "The following devices appear in the mechanical schedule and on the drawings "
            "but have no BMS control sequence in the Sequence of Operations. "
            "Scope confirmation is required from the engineer before final pricing:\n"
            + "\n".join(f"  - {t}" for t in amber)
        )

    exclusions = ""
    if red:
        exclusions = (
            "\n\nEXCLUSIONS:\n"
            "The following devices were listed in the mechanical schedule but were not "
            "identified on the drawing set reviewed. These items are excluded from this proposal "
            "pending clarification:\n"
            + "\n".join(f"  - {t}" for t in red)
        )

    if existing:
        p["proposal"]["text"] = existing + clarifications + exclusions
    else:
        p["proposal"]["text"] = (
            f"[Auto-generated from drawing markup — {p['name']}]\n"
            + clarifications + exclusions
        )

    p["proposal"]["status"] = "in_progress"
