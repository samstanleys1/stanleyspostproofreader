"""Streamlit web app for the Proofreader tool."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import anthropic
import streamlit as st

from proofreader import (
    BRAND_GUIDELINES_PATH,
    BRAND_RULES_PATH,
    LANGUAGE_TO_CTA_SHEET,
    SYSTEM_PROMPT,
    build_content_blocks,
    format_report,
)

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGO_PATH = ASSETS_DIR / "stanleys_post_logo.jpeg"

# --------------- page config ---------------
st.set_page_config(page_title="Proofreader", page_icon=":mag:", layout="wide")

# --------------- header ---------------
if LOGO_PATH.exists():
    st.image(str(LOGO_PATH), width=260)

st.title("Proofreader")
st.markdown(
    "Upload a product image to check for spelling, grammar, translation, "
    "and brand-compliance issues."
)

# --------------- sidebar ---------------
with st.sidebar:
    st.header("Settings")

    api_key = st.text_input("Anthropic API Key", type="password")

    languages = st.multiselect(
        "Expected languages",
        options=[lang.title() for lang in sorted(LANGUAGE_TO_CTA_SHEET.keys())],
        default=["English"],
    )

    asset_type = st.selectbox(
        "Asset Type",
        options=[
            "General",
            "LRD (Living Room Display)",
            "OOH (Out of Home - Print)",
            "DOOH (Digital Out of Home)",
            "Digital Display",
            "Companion Banners",
            "T-Sides (Bus Advertising)",
        ],
        index=0,
        help="Select the type of asset to apply specific compliance rules",
    )

    is_prime_original = st.checkbox(
        "Prime Original content",
        value=False,
        help="Check if this is a Prime Original movie/series (affects logo and CTA requirements)",
    )

    guidelines_file = st.file_uploader(
        "Brand guidelines (optional)",
        type=["pdf", "png", "jpg", "jpeg", "webp"],
    )

    # Show info about auto-loaded brand compliance files
    brand_files_loaded = []
    if BRAND_RULES_PATH.exists():
        brand_files_loaded.append(f"✓ Brand rules: {BRAND_RULES_PATH.name}")
    if BRAND_GUIDELINES_PATH.exists() and guidelines_file is None:
        brand_files_loaded.append(f"✓ Visual examples: {BRAND_GUIDELINES_PATH.name}")

    if brand_files_loaded:
        st.success("\n\n".join(brand_files_loaded))

# --------------- main area ---------------
uploaded_images = st.file_uploader(
    "Upload image(s) to proofread",
    type=["jpg", "jpeg", "png", "gif", "webp"],
    accept_multiple_files=True,
    help="You can upload multiple images at once (max 500MB per file)",
)

if uploaded_images:
    st.info(f"📁 {len(uploaded_images)} image(s) uploaded")

    if st.button("Analyze All", type="primary"):
        if not api_key:
            st.error("Please enter your Anthropic API key in the sidebar.")
            st.stop()

        # Prepare guidelines path (same for all images)
        guidelines_path: Path | None = None
        if guidelines_file is not None:
            with tempfile.NamedTemporaryFile(
                suffix=Path(guidelines_file.name).suffix, delete=False
            ) as tmp_guide:
                tmp_guide.write(guidelines_file.getvalue())
                guidelines_path = Path(tmp_guide.name)
        elif BRAND_GUIDELINES_PATH.exists():
            # Auto-load default brand guidelines if no custom file uploaded
            guidelines_path = BRAND_GUIDELINES_PATH

        languages_str = ", ".join(languages) if languages else "English"
        client = anthropic.Anthropic(api_key=api_key)

        # Process each image
        for img_idx, uploaded_image in enumerate(uploaded_images, 1):
            st.divider()
            st.header(f"Image {img_idx}/{len(uploaded_images)}: {uploaded_image.name}")
            st.image(uploaded_image, caption=uploaded_image.name, use_container_width=True)

            # Save uploaded file to temp path
            with tempfile.NamedTemporaryFile(
                suffix=Path(uploaded_image.name).suffix, delete=False
            ) as tmp_img:
                tmp_img.write(uploaded_image.getvalue())
                tmp_img_path = Path(tmp_img.name)

            with st.spinner(f"Analyzing {uploaded_image.name}..."):
                content = build_content_blocks(tmp_img_path, guidelines_path, languages_str, asset_type, is_prime_original)

                response = client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": content}],
                )

                raw_text = response.content[0].text

                try:
                    data = json.loads(raw_text)
                except json.JSONDecodeError:
                    match = re.search(
                        r"```(?:json)?\s*\n?(.*?)\n?```", raw_text, re.DOTALL
                    )
                    if match:
                        data = json.loads(match.group(1))
                    else:
                        st.error(f"Could not parse API response for {uploaded_image.name}")
                        st.code(raw_text)
                        continue

            # ---- display report ----
            st.subheader("Extracted Text")
            st.text(data.get("extracted_text", "(none)"))

            langs_detected = data.get("languages_detected", [])
            if langs_detected:
                st.subheader("Languages Detected")
                st.write(", ".join(langs_detected))

            issues = data.get("issues", [])
            st.subheader(f"Issues ({len(issues)} found)")

            if not issues:
                st.success("No issues found!")
            else:
                SEVERITY_COLORS = {
                    "error": "#ff4b4b",
                    "warning": "#faca2b",
                    "info": "#4b8bff",
                }
                for i, issue in enumerate(issues, 1):
                    severity = issue.get("severity", "info")
                    color = SEVERITY_COLORS.get(severity, SEVERITY_COLORS["info"])
                    category = issue.get("category", "unknown").upper()
                    label = f"{i}. [{severity.upper()}] {category}"

                    st.markdown(
                        f'<div style="border-left:4px solid {color}; padding:8px 12px; '
                        f'margin-bottom:8px; background:{color}18; border-radius:4px;">'
                        f"<strong>{label}</strong></div>",
                        unsafe_allow_html=True,
                    )
                    cols = st.columns([1, 3])
                    with cols[0]:
                        if issue.get("location"):
                            st.markdown(f"**Location**")
                        if issue.get("text"):
                            st.markdown(f"**Text**")
                        st.markdown("**Problem**")
                        st.markdown("**Suggestion**")
                    with cols[1]:
                        if issue.get("location"):
                            st.write(issue["location"])
                        if issue.get("text"):
                            st.write(issue["text"])
                        st.write(issue.get("problem", "N/A"))
                        st.write(issue.get("suggestion", "N/A"))

            summary = data.get("summary", "")
            if summary:
                st.subheader("Summary")
                st.info(summary)

            # ---- download button ----
            report_text = format_report(data)
            st.download_button(
                label=f"Download report for {uploaded_image.name}",
                data=report_text,
                file_name=f"proofreader_report_{uploaded_image.name}.txt",
                mime="text/plain",
                key=f"download_{img_idx}",
            )
