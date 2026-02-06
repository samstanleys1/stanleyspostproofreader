# Proofreader Tool

CLI tool that proofreads JPEG images (product packaging, marketing materials) using Claude's vision API.

## Usage

```bash
python proofreader.py photo.jpg --guidelines brand_guide.pdf --languages "English, Spanish"
python proofreader.py photo.jpg --output report.txt
```

## How it works

- Sends the JPEG and optional brand guidelines to Claude in a single API call
- Claude performs OCR, spelling/grammar checks, translation verification, and logo/visual analysis
- Results are printed as a formatted terminal report

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...
```

## Key design decisions

- Single API call with multi-image input keeps code simple
- No local OCR/NLP dependencies — everything runs through Claude's vision API
- API key via `ANTHROPIC_API_KEY` environment variable (standard for anthropic SDK)
