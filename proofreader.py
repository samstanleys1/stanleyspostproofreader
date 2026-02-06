#!/usr/bin/env python3
"""Proofreader tool: checks JPEG images for spelling, grammar, translation, and brand guideline issues using Claude's vision API."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import sys
from pathlib import Path

import anthropic
import openpyxl

SCRIPT_DIR = Path(__file__).resolve().parent
REFERENCES_DIR = SCRIPT_DIR / "references"
EMEA_PATH = REFERENCES_DIR / "EMEA Messaging Matrix-2[95].xlsx"
GLOBAL_CTA_PATH = REFERENCES_DIR / "Global_CTA_Matrix_Original Movies  Series_MASTER_ Dropdown_8.1.25-2.xlsx"

SYSTEM_PROMPT = """You are an expert proofreader and brand compliance reviewer. You will be given an image (product packaging, marketing material, etc.) and possibly a brand guidelines document.

Your job:
1. **OCR**: Extract ALL visible text from the image.
2. **Spelling**: Check every word for spelling errors in each detected language.
3. **Grammar**: Carefully check for grammar mistakes in all text. Pay close attention to subject-verb agreement (e.g., "battery life last" should be "battery life lasts"), incorrect tense, missing articles, wrong prepositions, and sentence structure errors. Report every grammar issue you find — do not skip any.
4. **Translation**: If multiple languages are expected, verify translations are accurate and consistent between languages.
5. **Approved Messaging Compliance**: If reference translation/messaging data is provided, compare ALL text in the image against the approved translations. Flag any text that uses unapproved wording, wrong capitalization style, or deviates from the approved CTAs and messaging.
6. **Visual/Brand Compliance**: If brand guidelines are provided, compare logo sizes, placement, colors, and typography against the guidelines. Note any deviations.

Return your analysis as a JSON object with this exact structure:
{
  "extracted_text": "All text found in the image, preserving layout as much as possible",
  "languages_detected": ["English", "Spanish"],
  "issues": [
    {
      "category": "spelling" | "grammar" | "translation" | "messaging_compliance" | "brand_compliance" | "visual",
      "severity": "error" | "warning" | "info",
      "location": "Description of where on the image (e.g., 'front panel, top-right')",
      "text": "The problematic text or element",
      "problem": "What is wrong",
      "suggestion": "Suggested fix"
    }
  ],
  "summary": "Brief overall assessment"
}

Return ONLY the JSON object, no other text. If there are no issues in a category, still return the JSON with an empty issues array."""


# Map common language names to spreadsheet identifiers
LANGUAGE_TO_EMEA_COL = {
    "english": "EN (English)", "german": "DE (German)", "french": "FR (French)",
    "italian": "IT (Italian)", "spanish": "ES (Spanish)", "dutch": "NL (Dutch)",
    "swedish": "SE (Swedish)", "norwegian": "NO (Norwegian)", "danish": "DK (Danish)",
    "finnish": "FI (Finnish)", "portuguese": "PT (Portuguese)", "polish": "PL (Polish)",
    "turkish": "TR (Turkish)", "romanian": "RO (Romanian)", "czech": "CZ (Czech)",
    "hungarian": "HU (Hungarian)", "greek": "GR (Greek)",
}

LANGUAGE_TO_CTA_SHEET = {
    "english": "en-US", "german": "de-DE", "french": "fr-FR",
    "italian": "it-IT", "spanish": "es-ES", "dutch": "nl-NL",
    "swedish": "sv-SE", "norwegian": "nb-NO", "danish": "da-DK",
    "finnish": "fi-FI", "portuguese": "pt-PT", "polish": "pl-PL",
    "turkish": "tr-TR", "romanian": "ro-RO", "czech": "cs-CZ",
    "hungarian": "hu-HU", "greek": "el-GR", "arabic": "ar-AE",
    "japanese": "ja-JP", "korean": "ko-KR",
}


def extract_emea_references(languages: list[str]) -> str:
    """Extract relevant columns from the EMEA Messaging Matrix for the given languages."""
    if not EMEA_PATH.exists():
        return ""

    wb = openpyxl.load_workbook(EMEA_PATH, read_only=True, data_only=True)
    ws = wb["EMEA Messaging Matrix"]

    # Find header row and column indices
    header_row = list(ws.iter_rows(min_row=1, max_row=1, values_only=True))[0]

    # Always include English + requested languages
    lang_keys = {"english"} | {l.strip().lower() for l in languages}
    col_indices = {}
    for lang_key in lang_keys:
        col_name = LANGUAGE_TO_EMEA_COL.get(lang_key)
        if col_name:
            for idx, val in enumerate(header_row):
                if val and col_name in str(val):
                    col_indices[col_name] = idx
                    break

    if not col_indices:
        wb.close()
        return ""

    # Extract the SOP guidelines column (col 0) + language columns
    lines = ["## EMEA Messaging Matrix — Approved Translations\n"]
    for row in ws.iter_rows(min_row=5, values_only=True):
        row_list = list(row)
        guideline = row_list[0] if row_list[0] else ""
        entries = {}
        for col_name, idx in col_indices.items():
            val = row_list[idx] if idx < len(row_list) and row_list[idx] else ""
            if val:
                entries[col_name] = str(val).strip()
        if entries:
            if guideline:
                lines.append(f"Context: {guideline}")
            for col_name, val in entries.items():
                lines.append(f"  {col_name}: {val}")
            lines.append("")

    wb.close()
    return "\n".join(lines)


def extract_cta_references(languages: list[str]) -> str:
    """Extract relevant sheets from the Global CTA Matrix for the given languages."""
    if not GLOBAL_CTA_PATH.exists():
        return ""

    wb = openpyxl.load_workbook(GLOBAL_CTA_PATH, read_only=True, data_only=True)

    # Always include en-US + requested languages
    lang_keys = {"english"} | {l.strip().lower() for l in languages}
    sheets_to_read = set()
    for lang_key in lang_keys:
        sheet_name = LANGUAGE_TO_CTA_SHEET.get(lang_key)
        if sheet_name and sheet_name in wb.sheetnames:
            sheets_to_read.add(sheet_name)

    if not sheets_to_read:
        wb.close()
        return ""

    lines = ["## Global CTA Matrix — Approved Messaging\n"]
    for sheet_name in sorted(sheets_to_read):
        ws = wb[sheet_name]
        lines.append(f"### Locale: {sheet_name}\n")
        for row in ws.iter_rows(min_row=14, values_only=True):
            row_list = list(row)
            # Columns: context (B=1), messaging EN (C=2), messaging local (D=3),
            # title case (E=4), sentence case (F=5), upper case (G=6)
            context = row_list[1] if len(row_list) > 1 and row_list[1] else ""
            msg_en = row_list[2] if len(row_list) > 2 and row_list[2] else ""
            msg_local = row_list[3] if len(row_list) > 3 and row_list[3] else ""
            title_case = row_list[4] if len(row_list) > 4 and row_list[4] else ""
            sentence_case = row_list[5] if len(row_list) > 5 and row_list[5] else ""
            upper_case = row_list[6] if len(row_list) > 6 and row_list[6] else ""

            if any([msg_en, msg_local, title_case, sentence_case, upper_case]):
                parts = []
                if context:
                    parts.append(f"Context: {str(context).strip()}")
                if msg_en:
                    parts.append(f"  EN: {str(msg_en).strip()}")
                if msg_local:
                    parts.append(f"  Local: {str(msg_local).strip()}")
                if title_case:
                    parts.append(f"  Title Case: {str(title_case).strip()}")
                if sentence_case:
                    parts.append(f"  Sentence Case: {str(sentence_case).strip()}")
                if upper_case:
                    parts.append(f"  Upper Case: {str(upper_case).strip()}")
                lines.append("\n".join(parts))
                lines.append("")

    wb.close()
    return "\n".join(lines)


def load_reference_data(languages: list[str]) -> str:
    """Load all reference data for the given languages."""
    parts = []

    emea = extract_emea_references(languages)
    if emea:
        parts.append(emea)

    cta = extract_cta_references(languages)
    if cta:
        parts.append(cta)

    if not parts:
        return ""

    header = (
        "=== REFERENCE DATA: Approved Translations & Messaging ===\n"
        "The following are the officially approved translations and CTAs. "
        "Compare ALL text in the image against these references. "
        "Flag any text that does not match the approved translations — "
        "wrong wording, wrong capitalization, or unapproved messaging.\n\n"
    )
    return header + "\n\n".join(parts)


def encode_file(path: Path) -> tuple[str, str]:
    """Read a file and return (base64_data, media_type)."""
    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type is None:
        suffix = path.suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".pdf": "application/pdf",
        }
        mime_type = mime_map.get(suffix, "application/octet-stream")

    data = path.read_bytes()
    return base64.standard_b64encode(data).decode("utf-8"), mime_type


def build_content_blocks(image_path: Path, guidelines_path: Path | None, languages: str) -> list[dict]:
    """Build the content blocks for the Claude API request."""
    blocks = []

    # Add the main image
    img_data, img_mime = encode_file(image_path)
    blocks.append({
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": img_mime,
            "data": img_data,
        },
    })
    blocks.append({
        "type": "text",
        "text": f"Above is the image to proofread. Expected languages: {languages}.",
    })

    # Add guidelines if provided
    if guidelines_path:
        guide_data, guide_mime = encode_file(guidelines_path)
        if guide_mime == "application/pdf":
            blocks.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": guide_mime,
                    "data": guide_data,
                },
            })
        else:
            blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": guide_mime,
                    "data": guide_data,
                },
            })
        blocks.append({
            "type": "text",
            "text": "Above is the brand guidelines document. Compare the product image against these guidelines for compliance.",
        })

    # Add reference data from spreadsheets
    lang_list = [l.strip() for l in languages.split(",")]
    ref_data = load_reference_data(lang_list)
    if ref_data:
        blocks.append({
            "type": "text",
            "text": ref_data,
        })

    blocks.append({
        "type": "text",
        "text": "Analyze the image and return the JSON report.",
    })

    return blocks


def format_report(data: dict) -> str:
    """Format the JSON response into a readable terminal report."""
    lines = []
    lines.append("=" * 60)
    lines.append("  PROOFREADER REPORT")
    lines.append("=" * 60)

    # Extracted text
    lines.append("\n--- Extracted Text ---")
    lines.append(data.get("extracted_text", "(none)"))

    # Languages
    langs = data.get("languages_detected", [])
    if langs:
        lines.append(f"\n--- Languages Detected ---")
        lines.append(", ".join(langs))

    # Issues
    issues = data.get("issues", [])
    lines.append(f"\n--- Issues ({len(issues)} found) ---")

    if not issues:
        lines.append("No issues found.")
    else:
        severity_symbols = {"error": "[ERROR]", "warning": "[WARN] ", "info": "[INFO] "}
        for i, issue in enumerate(issues, 1):
            sev = severity_symbols.get(issue.get("severity", "info"), "[INFO] ")
            cat = issue.get("category", "unknown").upper()
            lines.append(f"\n  {i}. {sev} [{cat}]")
            if issue.get("location"):
                lines.append(f"     Location:   {issue['location']}")
            if issue.get("text"):
                lines.append(f"     Text:       {issue['text']}")
            lines.append(f"     Problem:    {issue.get('problem', 'N/A')}")
            lines.append(f"     Suggestion: {issue.get('suggestion', 'N/A')}")

    # Summary
    summary = data.get("summary", "")
    if summary:
        lines.append(f"\n--- Summary ---")
        lines.append(summary)

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Proofread JPEG images for spelling, grammar, translation, and brand compliance issues."
    )
    parser.add_argument("image", type=Path, help="Path to the JPEG image to proofread")
    parser.add_argument("--guidelines", type=Path, default=None, help="Path to brand guidelines (PDF or image)")
    parser.add_argument("--languages", type=str, default="English", help='Expected languages, comma-separated (default: "English")')
    parser.add_argument("--output", type=Path, default=None, help="Save report to a file")
    args = parser.parse_args()

    # Validate inputs
    if not args.image.exists():
        print(f"Error: Image file not found: {args.image}", file=sys.stderr)
        sys.exit(1)
    if args.guidelines and not args.guidelines.exists():
        print(f"Error: Guidelines file not found: {args.guidelines}", file=sys.stderr)
        sys.exit(1)

    # Build and send API request
    client = anthropic.Anthropic()
    content = build_content_blocks(args.image, args.guidelines, args.languages)

    print(f"Analyzing {args.image.name}...", file=sys.stderr)
    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    # Extract text response
    raw_text = response.content[0].text

    # Parse JSON from response
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        import re
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw_text, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
        else:
            print("Error: Could not parse API response as JSON.", file=sys.stderr)
            print("Raw response:", file=sys.stderr)
            print(raw_text, file=sys.stderr)
            sys.exit(1)

    # Format and print report
    report = format_report(data)
    print(report)

    # Save to file if requested
    if args.output:
        args.output.write_text(report)
        print(f"\nReport saved to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
