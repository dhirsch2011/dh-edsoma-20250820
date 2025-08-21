#!/usr/bin/env bash
set -euo pipefail

PDF_URL="https://raw.githubusercontent.com/dhirsch2011/dh-edsoma-20250820/090f7efe2815f05a1a3bc781085d61458242e3b6/ngmp-compressed_2.pdf"
PDF_PATH="/workspace/ngmp-compressed_2.pdf"
OUTPUT_ROOT="/workspace"
PREFIX="GNM_202505"

log() {
  printf "%s\n" "$*"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

try_install() {
  # Attempt to install poppler-utils and tesseract if missing
  if need_cmd apt-get; then
    APT=apt-get
  elif need_cmd apt; then
    APT=apt
  else
    APT=""
  fi

  if [ -n "${APT}" ]; then
    log "Installing missing dependencies via ${APT} (if needed)..."
    # Use sudo if available, otherwise run directly
    if need_cmd sudo; then SUDO="sudo"; else SUDO=""; fi
    set +e
    ${SUDO} ${APT} update -y >/dev/null 2>&1
    ${SUDO} ${APT} install -y poppler-utils tesseract-ocr >/dev/null 2>&1
    set -e
  else
    log "apt not available; ensure poppler-utils and tesseract are installed."
  fi
}

ensure_tools() {
  local missing=0
  for tool in pdftoppm pdfimages pdfinfo tesseract curl; do
    if ! need_cmd "$tool"; then
      log "Missing tool: $tool"
      missing=1
    fi
  done
  if [ "$missing" -eq 1 ]; then
    try_install
  fi

  # Re-check critical tools
  for tool in pdftoppm pdfimages pdfinfo tesseract curl; do
    if ! need_cmd "$tool"; then
      log "Error: required tool not found: $tool"
      exit 1
    fi
  done
}

download_pdf() {
  if [ -f "$PDF_PATH" ]; then
    log "PDF already exists at $PDF_PATH; re-downloading to ensure freshness..."
  fi
  curl -L --fail -o "$PDF_PATH" "$PDF_URL"
}

get_num_pages() {
  pdfinfo "$PDF_PATH" | awk '/^Pages:/ {print $2}'
}

render_page_png() {
  local page_number="$1"
  local out_dir="$2"
  # Render single page to PNG named page.png
  pdftoppm -r 400 -gray -aa yes -aaVector yes -f "$page_number" -l "$page_number" -singlefile -png "$PDF_PATH" "$out_dir/page"
}

ocr_page() {
  local out_dir="$1"
  tesseract "$out_dir/page.png" "$out_dir/text" -l eng --oem 1 --psm 6 --dpi 400 >/dev/null 2>&1
}

extract_images_for_page() {
  local page_number="$1"
  local out_dir="$2"
  pdfimages -p -all -f "$page_number" -l "$page_number" "$PDF_PATH" "$out_dir/images" >/dev/null 2>&1 || true
}

main() {
  log "Ensuring required tools are available..."
  ensure_tools

  log "Downloading PDF..."
  download_pdf

  log "Determining page count..."
  local pages
  pages="$(get_num_pages)"
  if ! [[ "$pages" =~ ^[0-9]+$ ]]; then
    log "Error: Could not determine number of pages. Got: '$pages'"
    exit 1
  fi
  log "Processing $pages pages."

  for ((p=1; p<=pages; p++)); do
    dir_name=$(printf "%s_%03d" "$PREFIX" "$p")
    out_dir="$OUTPUT_ROOT/$dir_name"
    mkdir -p "$out_dir"
    log "[Page $p/$pages] Rendering PNG..."
    render_page_png "$p" "$out_dir"
    log "[Page $p/$pages] OCR to text.txt..."
    ocr_page "$out_dir"
    log "[Page $p/$pages] Extracting embedded images..."
    extract_images_for_page "$p" "$out_dir"
  done

  log "All done. Output created under $OUTPUT_ROOT as ${PREFIX}_NNN per page."
}

main "$@"

