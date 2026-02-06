"""Streamlit web app for the Proofreader tool."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import anthropic
import streamlit as st

from proofreader import (
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

    guidelines_file = st.file_uploader(
        "Brand guidelines (optional)",
        type=["pdf", "png", "jpg", "jpeg", "webp"],
    )

# --------------- main area ---------------
uploaded_image = st.file_uploader(
    "Upload an image to proofread",
    type=["jpg", "jpeg", "png", "gif", "webp"],
)

if uploaded_image is not None:
    st.image(uploaded_image, caption="Uploaded image", use_container_width=True)

    if st.button("Analyze", type="primary"):
        if not api_key:
            st.error("Please enter your Anthropic API key in the sidebar.")
            st.stop()
        # Save uploaded files to temp paths so existing helpers can read them
        with tempfile.NamedTemporaryFile(
            suffix=Path(uploaded_image.name).suffix, delete=False
        ) as tmp_img:
            tmp_img.write(uploaded_image.getvalue())
            tmp_img_path = Path(tmp_img.name)

        guidelines_path: Path | None = None
        if guidelines_file is not None:
            with tempfile.NamedTemporaryFile(
                suffix=Path(guidelines_file.name).suffix, delete=False
            ) as tmp_guide:
                tmp_guide.write(guidelines_file.getvalue())
                guidelines_path = Path(tmp_guide.name)

        languages_str = ", ".join(languages) if languages else "English"

        with st.spinner("Analyzing..."):
            content = build_content_blocks(tmp_img_path, guidelines_path, languages_str)

            client = anthropic.Anthropic(api_key=api_key)
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
                    st.error("Could not parse API response as JSON.")
                    st.code(raw_text)
                    st.stop()

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
            label="Download report as text",
            data=report_text,
            file_name="proofreader_report.txt",
            mime="text/plain",
        )
