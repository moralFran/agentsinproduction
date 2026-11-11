#!/usr/bin/env bash
# Display filter for live agent output in the video: drop markdown bold markers, wrap at word boundaries.
tr -d '*' | fold -s -w 76
