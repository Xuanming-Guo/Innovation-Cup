#!/bin/sh
cd "$(dirname "$0")" || exit 1
node scripts/local-host.mjs start
status=$?
if [ "$status" -ne 0 ]; then
  printf '\nPress Return to close...'
  read -r _answer
fi
exit "$status"
