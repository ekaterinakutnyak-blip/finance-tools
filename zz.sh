#!/bin/bash
# zz — заливка файлов из GitHub на сайт.
# Использование:  zz novosti/portfeli-biotech-5050.html novosti/portfeli-robototehnika.html
R=https://raw.githubusercontent.com/ekaterinakutnyak-blip/finance-tools/main
cd /var/www/html || exit 1
for f in "$@"; do
  if wget -q --no-cache -O "$f.tmp" "$R/$f?v=$RANDOM"; then
    mv "$f.tmp" "$f"
    echo "OK   $(stat -c %s "$f") байт   $f"
  else
    rm -f "$f.tmp"
    echo "НЕТ В GITHUB   $f"
  fi
done
