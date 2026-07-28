#!/usr/bin/env bash
#
# sp500_by_founding_year.sh
#
# Downloads the S&P 500 constituents CSV and prints Company Name,
# Headquarters Location, and Founding Year — sorted by founding year
# (oldest first).
#
# Usage:
#   ./sp500_by_founding_year.sh
#   ./sp500_by_founding_year.sh --desc                # newest first
#   ./sp500_by_founding_year.sh --out companies.csv    # save as CSV instead of printing a table
#
# Requires: curl, gawk (GNU awk — needed for FPAT to parse quoted CSV fields
# correctly, since some "Founded" values contain commas inside quotes, e.g.
# "2020 (1915, United Technologies spinoff)").

set -euo pipefail

URL="https://raw.githubusercontent.com/datasets/s-and-p-500-companies/refs/heads/main/data/constituents.csv"

SORT_ORDER="asc"
OUT_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --desc) SORT_ORDER="desc"; shift ;;
    --asc) SORT_ORDER="asc"; shift ;;
    --out) OUT_FILE="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if ! command -v gawk >/dev/null 2>&1; then
  echo "This script requires GNU awk (gawk). Install it, e.g.:" >&2
  echo "  macOS:  brew install gawk" >&2
  echo "  Debian/Ubuntu: sudo apt-get install gawk" >&2
  exit 1
fi

TMP_CSV="$(mktemp)"
trap 'rm -f "$TMP_CSV"' EXIT

curl -fsSL "$URL" -o "$TMP_CSV"

# Parse the CSV with FPAT so quoted commas don't split fields, pull out
# Security (name), Headquarters Location, and Founded, then compute a
# numeric sort key from the first 4-digit year found in "Founded"
# (handles values like "2020 (1915, United Technologies spinoff)").
PARSED="$(gawk '
  BEGIN {
    FPAT = "([^,]*)|(\"[^\"]*\")"
    OFS = "\t"
  }
  NR == 1 { next }  # skip header
  {
    name = $2; gsub(/^"|"$/, "", name)
    loc  = $5; gsub(/^"|"$/, "", loc)
    founded = $8; gsub(/^"|"$/, "", founded)

    year = founded
    if (match(year, /[0-9]{4}/)) {
      year = substr(year, RSTART, RLENGTH)
    } else {
      year = "9999"  # unknown years sort last in ascending order
    }
    print year, name, loc, founded
  }
' "$TMP_CSV")"

if [[ "$SORT_ORDER" == "asc" ]]; then
  SORTED="$(echo "$PARSED" | sort -t$'\t' -k1,1n)"
else
  SORTED="$(echo "$PARSED" | sort -t$'\t' -k1,1nr)"
fi

if [[ -n "$OUT_FILE" ]]; then
  {
    echo "Company Name,Headquarters Location,Founded"
    echo "$SORTED" | awk -F'\t' 'BEGIN{OFS=","} {
      gsub(/"/,"\"\"",$2); gsub(/"/,"\"\"",$3); gsub(/"/,"\"\"",$4);
      print "\"" $2 "\",\"" $3 "\",\"" $4 "\""
    }'
  } > "$OUT_FILE"
  echo "Saved to $OUT_FILE"
else
  printf "%-40s %-45s %s\n" "COMPANY" "LOCATION" "FOUNDED"
  echo "$SORTED" | awk -F'\t' '{ printf "%-40s %-45s %s\n", $2, $3, $4 }'
fi