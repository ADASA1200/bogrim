#!/usr/bin/env bash
# מוריד את "מקרא על פי המסורה" (CC BY-SA) מ-Sefaria, ספר אחרי ספר, לתיקייה שמקבלים כפרמטר.
# אחר כך: node scripts/build-tanach.mjs <התיקייה>
set -euo pipefail
out="${1:?usage: fetch-tanach.sh <dir>}"
mkdir -p "$out"
here="$(cd "$(dirname "$0")" && pwd)"
while IFS=$'\t' read -r en he; do
  f="$out/$(echo "$en" | tr ' ' '_').json"
  [ -s "$f" ] && continue
  echo "$he"
  curl -sS --fail -m 120 --retry 3 -G "https://www.sefaria.org/api/v3/texts/${en// /%20}" \
    --data-urlencode "version=hebrew|Miqra_according_to_the_Masorah" -o "$f"
done < "$here/tanach-books.tsv"
