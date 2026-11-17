# gw <run>: the lab gateway's own log lines for one run, every line except the forwarded calls (run opened, refusals,
# run closed), printed as text by jq. Fields are read from the log as they are; nothing is added.
gw() {
  jq -r --arg r "$1" 'select(.run == $r and .verdict != "forwarded")
    | [(.event // .verdict), (.why // "cap $\(.cap_usd)   spent $\(.spent_usd)   calls \(.calls)")] | join("   ")' gateway.log
}
