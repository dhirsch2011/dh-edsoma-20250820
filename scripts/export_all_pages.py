#!/usr/bin/env python
import argparse
import os
import subprocess
import sys
from typing import List

from pypdf import PdfReader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Loop all PDF pages and call export_page_assets.py per page.")
    parser.add_argument("--pdf", required=True, help="Path to source PDF")
    parser.add_argument("--out-dir", required=True, help="Base output directory for page folders")
    parser.add_argument("--prefix", required=True, help="Prefix for per-page folder names")
    parser.add_argument("--dpi", type=int, default=450, help="Rendering DPI (default 450)")
    parser.add_argument("--no-confusion", action="store_true", help="Disable confusion-map fixes in OCR")
    parser.add_argument("--no-spell", action="store_true", help="Disable spell-correction in OCR")
    parser.add_argument("--python", default=os.path.join("/workspace", ".venv", "bin", "python"), help="Python interpreter to use (defaults to venv)")
    return parser.parse_args()


def build_cmd(py: str, script_path: str, pdf_path: str, out_dir: str, prefix: str, dpi: int, page: int, no_confusion: bool, no_spell: bool) -> List[str]:
    cmd = [
        py,
        script_path,
        "--pdf",
        pdf_path,
        "--page",
        str(page),
        "--out-dir",
        out_dir,
        "--prefix",
        prefix,
        "--dpi",
        str(dpi),
    ]
    if no_confusion:
        cmd.append("--no-confusion")
    if no_spell:
        cmd.append("--no-spell")
    return cmd


def main() -> int:
    args = parse_args()
    if not os.path.exists(args.pdf):
        print(f"ERROR: PDF not found: {args.pdf}", file=sys.stderr)
        return 1

    os.makedirs(args.out_dir, exist_ok=True)

    # Get total number of pages using pypdf's PdfReader (as requested)
    reader = PdfReader(args.pdf)
    total_pages = len(reader.pages)

    script_path = os.path.join(os.path.dirname(__file__), "export_page_assets.py")
    if not os.path.exists(script_path):
        print(f"ERROR: export script not found at {script_path}", file=sys.stderr)
        return 1

    for page in range(1, total_pages + 1):
        cmd = build_cmd(
            py=args.python,
            script_path=script_path,
            pdf_path=args.pdf,
            out_dir=args.out_dir,
            prefix=args.prefix,
            dpi=args.dpi,
            page=page,
            no_confusion=args.no_confusion,
            no_spell=args.no_spell,
        )
        print("Running:", " ".join(cmd))
        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            print(f"ERROR: export failed for page {page}", file=sys.stderr)
            return proc.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

