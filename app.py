"""Streamlit web app for the Proofreader tool."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path

import anthropic
import streamlit as st
from dotenv import load_dotenv

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

# --------------- password protection ---------------
# Password is stored in environment variable or .env file
load_dotenv()

PROOFREADER_PASSWORD = os.getenv("PROOFREADER_PASSWORD", "proofreader2025")

# Initialize session state for authentication
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Show login screen if not authenticated
if not st.session_state.authenticated:
    st.title("🔒 Proofreader Access")
    st.markdown("Please enter the password to access the proofreader tool.")

    password_input = st.text_input("Password", type="password", key="password_input")

    if st.button("Login", type="primary"):
        if password_input == PROOFREADER_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("❌ Incorrect password. Please try again.")

    st.stop()

# --------------- header ---------------
if LOGO_PATH.exists():
    st.image(str(LOGO_PATH), width=260)

st.title("Proofreader")
st.markdown(
    "Upload a product image or PDF to check for spelling, grammar, translation, "
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

    pre_or_post = st.radio(
        "CTA Type (Release Status)",
        options=["Pre", "Post"],
        index=0,
        help="Pre = Before release (CTA must have a date). Post = After release (CTA must have 'Watch Now' or similar action copy)",
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
uploaded_files = st.file_uploader(
    "Upload file(s) to proofread",
    type=["jpg", "jpeg", "png", "gif", "webp", "pdf"],
    accept_multiple_files=True,
    help="You can upload multiple images or PDFs at once (max 500MB per file)",
)

if uploaded_files:
    st.info(f"📁 {len(uploaded_files)} file(s) uploaded")

    # Initialize session state for results
    if "analysis_results" not in st.session_state:
        st.session_state.analysis_results = {}

    if st.button("Analyze All", type="primary"):
        if not api_key:
            st.error("Please enter your Anthropic API key in the sidebar.")
            st.stop()

        # Clear previous results
        st.session_state.analysis_results = {}

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

        # Clean asset type (remove parenthetical descriptions)
        # e.g., "OOH (Out of Home - Print)" -> "OOH"
        asset_type_clean = asset_type.split(" (")[0] if " (" in asset_type else asset_type

        # Process each image
        for img_idx, uploaded_image in enumerate(uploaded_files, 1):
            # Save uploaded file to temp path
            with tempfile.NamedTemporaryFile(
                suffix=Path(uploaded_image.name).suffix, delete=False
            ) as tmp_img:
                tmp_img.write(uploaded_image.getvalue())
                tmp_img_path = Path(tmp_img.name)

            with st.spinner(f"Analyzing {uploaded_image.name}..."):
                content = build_content_blocks(tmp_img_path, guidelines_path, languages_str, asset_type_clean, is_prime_original, pre_or_post)

                # Retry logic for API overload errors
                max_retries = 5
                retry_delay = 2  # seconds

                for attempt in range(max_retries):
                    try:
                        response = client.messages.create(
                            model="claude-opus-4-6",
                            max_tokens=4096,
                            system=SYSTEM_PROMPT,
                            messages=[{"role": "user", "content": content}],
                        )
                        break  # Success, exit retry loop
                    except anthropic.APIStatusError as e:
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                            st.warning(f"⏳ API overloaded, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                            time.sleep(wait_time)
                        else:
                            st.error(f"❌ API overloaded after {max_retries} attempts. Please try again in a few minutes.")
                            st.stop()

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

                # Store results in session state
                st.session_state.analysis_results[uploaded_image.name] = data

    # ---- Display results (outside button block so it persists) ----
    if st.session_state.analysis_results:
        for img_idx, uploaded_image in enumerate(uploaded_files, 1):
            if uploaded_image.name not in st.session_state.analysis_results:
                continue

            data = st.session_state.analysis_results[uploaded_image.name]

            st.divider()
            is_pdf = uploaded_image.name.lower().endswith(".pdf")
            st.header(f"File {img_idx}/{len(uploaded_files)}: {uploaded_image.name}")
            if is_pdf:
                st.info(f"📄 PDF file: {uploaded_image.name}")
            else:
                st.image(uploaded_image, caption=uploaded_image.name, use_container_width=True)

            # ---- display report ----
            st.subheader("Extracted Text")
            st.text(data.get("extracted_text", "(none)"))

            langs_detected = data.get("languages_detected", [])
            if langs_detected:
                st.subheader("Languages Detected")
                st.write(", ".join(langs_detected))

            # Display element identification
            element_id = data.get("element_identification", {})
            if element_id:
                st.subheader("Element Identification")
                st.markdown("**What Claude identified in the image:**")
                cols = st.columns(2)
                with cols[0]:
                    if element_id.get("title_treatment"):
                        st.markdown(f"**Title Treatment (TT):** {element_id['title_treatment']}")
                    if element_id.get("signature"):
                        st.markdown(f"**Signature:** {element_id['signature']}")
                with cols[1]:
                    if element_id.get("cta"):
                        st.markdown(f"**CTA:** {element_id['cta']}")
                    if element_id.get("container_logo"):
                        st.markdown(f"**Container Logo:** {element_id['container_logo']}")

            issues = data.get("issues", [])
            st.subheader(f"Issues ({len(issues)} found)")

            # Initialize session state for issue selection
            # Reset if length doesn't match (happens when re-analyzing)
            if (f"selected_issues_{img_idx}" not in st.session_state or
                len(st.session_state[f"selected_issues_{img_idx}"]) != len(issues)):
                st.session_state[f"selected_issues_{img_idx}"] = [True] * len(issues)

            if not issues:
                st.success("No issues found!")
            else:
                st.info("✏️ Uncheck any false positives before downloading the report")

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

                    # Create columns: checkbox + issue details
                    checkbox_col, content_col = st.columns([0.5, 9.5])

                    with checkbox_col:
                        is_selected = st.checkbox(
                            "Include",
                            value=st.session_state[f"selected_issues_{img_idx}"][i-1],
                            key=f"issue_{img_idx}_{i}",
                            label_visibility="collapsed"
                        )
                        st.session_state[f"selected_issues_{img_idx}"][i-1] = is_selected

                    with content_col:
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
            # Create filtered data with only selected issues
            filtered_data = data.copy()
            if issues:
                selected_issues = [
                    issue for i, issue in enumerate(issues)
                    if st.session_state[f"selected_issues_{img_idx}"][i]
                ]
                filtered_data["issues"] = selected_issues

                # Update summary to reflect filtered count
                selected_count = len(selected_issues)
                total_count = len(issues)
                if selected_count < total_count:
                    st.info(f"📊 Report will include {selected_count} of {total_count} issues")

            report_text = format_report(filtered_data)
            st.download_button(
                label=f"Download report for {uploaded_image.name}",
                data=report_text,
                file_name=f"proofreader_report_{uploaded_image.name}.txt",
                mime="text/plain",
                key=f"download_{img_idx}",
            )
