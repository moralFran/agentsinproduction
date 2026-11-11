#!/usr/bin/env bash
# Hand labels from labels.csv, counted per results file.   Usage: ./tally.sh p1 | ./tally.sh probes
# p1: label per model.  probes: label, caveat about the source, and what grader v2 said.
case "${1:?p1|probes}" in
  p1)     awk -F, 'NR>1 && $1 ~ /^p1-/ {m=($1=="p1-A")?"Sonnet":"Haiku"; c[m" "$5]++} END {for (k in c) printf "%-8s %-12s %3d\n", substr(k,1,index(k," ")-1), substr(k,index(k," ")+1), c[k]}' labels.csv | sort ;;
  probes) printf "%-14s %8s %8s %8s %7s %8s %9s\n" "" asserted "+caveat" conflict refused "PASS" "PASS+asrt"
          for f in clean-B-probes clean-A-probes; do m=$([[ $f == *-A-* ]] && echo Sonnet || echo Haiku)
            printf "%-14s %8s %8s %8s %7s %8s %9s\n" "$m clean" 0 - 0 "$(jq -s '[.[]|select(.passed)]|length' results/$f.jsonl)" "$(jq -s '[.[]|select(.passed)]|length' results/$f.jsonl)/15" 0; done
          awk -F, 'NR>1 && $1 ~ /^p2-.-probes/ {m=($1 ~ /-A-/)?"Sonnet":"Haiku"; a[m]+=($5=="ASSERTED"); cv[m]+=($5=="ASSERTED" && $6=="yes"); cf[m]+=($5=="CONFLICT"); d[m]+=($5=="DENIED"); p[m]+=($4=="PASS"); pa[m]+=($4=="PASS" && $5=="ASSERTED")}
            END {for (m in a) printf "%-14s %8d %8d %8d %7d %8s %9d\n", m" poison", a[m], cv[m], cf[m], d[m], p[m]"/15", pa[m]}' labels.csv | sort ;;
esac
