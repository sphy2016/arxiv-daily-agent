#!/bin/zsh
# Usage: ./run.sh [run|fb|interest|consolidate|status] ...   (default: run)
cd "${0:A:h}"
[[ $# -eq 0 ]] && set -- run
exec python3 -m arxiv_daily "$@"
