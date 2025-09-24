#!/usr/bin/env python3
import argparse
import io
import os
import re
import sys


def clean_and_first_sentence(text: str) -> str:
    # Undo hyphenation across line breaks: e.g., work-\n ing -> working
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    # Replace newlines/tabs with spaces then collapse whitespace
    text = text.replace("\r", "\n")
    text = text.replace("\t", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    # Take up to the first period included
    period_idx = text.find('.')
    if period_idx != -1:
        sentence = text[: period_idx + 1]
    else:
        sentence = text
    return "\t" + sentence


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize OCR output to the first sentence with a leading tab")
    parser.add_argument("input", help="Path to OCR text input file")
    parser.add_argument("output", help="Path to write cleaned sentence .txt")
    args = parser.parse_args()

    with io.open(args.input, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()
    cleaned = clean_and_first_sentence(raw)
    # Ensure trailing newline for POSIX text files
    with io.open(args.output, "w", encoding="utf-8") as f:
        f.write(cleaned)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

