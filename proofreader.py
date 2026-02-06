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

SYSTEM_PROMPT = """You are an expert proofreader and brand compliance reviewer. You will be given an image (product packaging, marketing material, etc.) and possibly a brand guidelines document.

Your job:
1. **OCR**: Extract ALL visible text from the image.
2. **Spelling**: Check every word for spelling errors in each detected language.
3. **Grammar**: Carefully check for grammar mistakes in all text. Pay close attention to subject-verb agreement (e.g., "battery life last" should be "battery life lasts"), incorrect tense, missing articles, wrong prepositions, and sentence structure errors. Report every grammar issue you find — do not skip any.
4. **Translation**: If multiple languages are expected, verify translations are accurate and consistent between languages.
5. **Visual/Brand Compliance**: If brand guidelines are provided, compare logo sizes, placement, colors, and typography against the guidelines. Note any deviations.

Return your analysis as a JSON object with this exact structure:
{
  "extracted_text": "All text found in the image, preserving layout as much as possible",
  "languages_detected": ["English", "Spanish"],
  "issues": [
    {
      "category": "spelling" | "grammar" | "translation" | "brand_compliance" | "visual",
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
