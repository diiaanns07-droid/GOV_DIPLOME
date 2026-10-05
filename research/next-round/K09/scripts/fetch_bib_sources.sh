#!/usr/bin/env bash
# K09: воспроизводимое получение файлов авторов, по которым проверялась библиография.
# Берёт только указанные файлы (blobless clone + checkout путей) на закреплённых коммитах.
# Использование: bash fetch_bib_sources.sh <рабочая_папка>
# Затем: sha256sum -c ../sources/SHA256SUMS.txt (из рабочей папки).
set -euo pipefail
OUT="${1:?укажите рабочую папку}"
mkdir -p "$OUT"; cd "$OUT"
get() { # repo commit path...
  local repo="$1" sha="$2"; shift 2
  local d="${repo//\//_}"
  [ -d "$d/.git" ] || GIT_LFS_SKIP_SMUDGE=1 git clone -q --filter=blob:none --no-checkout "https://github.com/$repo" "$d"
  git -C "$d" fetch -q --depth 1 origin "$sha" 2>/dev/null || true
  git -C "$d" checkout -q "$sha" -- "$@"
}
get quaquel/EMAworkbench      3798b375bc4208356a74432e67040f38c6cf75a5 CITATION.cff README.md
get Project-Platypus/Rhodium  1c09159c5b06fc0784ecfe13383c7a06a611d4e1 README.md
get SALib/SALib               c8b2be52a136d861caf4b1e53a4dae2e036ee390 CITATION.cff CITATIONS.rst paper/paper.md paper/codemeta.json
get gboeing/osmnx             74e68ce2200b23c04f6ec2a864a6c24859bbf08d CITATION.cff README.md
get princeton-nlp/ALCE        246c476a4edfc564266b7346b6e29ef4861ae937 README.md paper/ALCE.pdf
get greshake/llm-security     c312325bee5f16d8f6524bd6f41e1510c5623a1e README.md
get nl4opt/nl4opt-competition 49f1e0d66b7fdcd33305a7f281c2a7c13f5620ea README.md
get teshnizi/OptiMUS          59e8d99653459b40361f618eafdc91eee3a85ebb README.md
get reasoning-machines/pal    f81ca2a9777f002f98a6b4d0f10b61bd5c8feb02 CITATION.cff README.md
get r5py/r5py                 59c97d0a65f9b0dfd9488d0084613c96e0d92c45 README.md docs/user-guide/citation.md docs/_static/references.bib
# Полный текст ALCE (препринт в репозитории авторов) -> текст для поиска по локаторам
command -v pdftotext >/dev/null && pdftotext -layout princeton-nlp_ALCE/paper/ALCE.pdf alce.txt || echo "pdftotext не найден: alce.txt не создан"
