#!/usr/bin/env bash
# Заново выгружает data/ из исходных репозиториев на коммитах из repos.txt.
# Нужен, только если вы хотите проверить сами данные: run.sh работает без него.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .cache data

while read -r name url sha; do
  dir=".cache/$name"
  if [ ! -d "$dir" ]; then
    git clone --quiet --no-checkout "$url" "$dir"
  fi
  if ! git -C "$dir" cat-file -e "$sha^{commit}" 2>/dev/null; then
    git -C "$dir" fetch --quiet origin
  fi
  git -C "$dir" cat-file -e "$sha^{commit}"
  python3 extract.py "$dir" "$name" "$sha"
  echo "$name: $(grep -c '^C' "data/$name.tsv") коммитов"
done < repos.txt
