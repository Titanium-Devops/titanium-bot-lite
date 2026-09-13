#!/usr/bin/env bash
# Step 0: ten minutes with the Tiiny. Usage:
#   TIINY_KEY=... [TIINY_BASE=http://<device-ip>/v1] [TIINY_MODEL=<model id>] bash scripts/probe-device.sh
# Without TIINY_BASE it asks lite/device.py to find the box.
# Prints status codes and short answers only. Never paste the key into a chat or a screenshot.
set -u
: "${TIINY_KEY:?set TIINY_KEY (TiinyOS > Settings > API Key)}"
B="${TIINY_BASE:-$(python3 -c 'from lite import device; print(device.find_base())')}"
: "${B:?no Tiiny found; set TIINY_BASE to http://<device-ip>/v1}"
M="${TIINY_MODEL:-default}"
H=(-H "Authorization: Bearer $TIINY_KEY" -H "Content-Type: application/json")
say() { printf '\n== %s\n' "$*"; }
json() { python3 -c 'import json,sys; print(json.dumps(json.loads(sys.argv[1])))' "$1"; }
say "1. models"; curl -s -m 15 "${H[@]}" "$B/models" | head -c 700; echo
say "2. chat, plain ($M)"; curl -s -m 90 "${H[@]}" "$B/chat/completions" -d "$(json '{"model":"'"$M"'","messages":[{"role":"user","content":"Say hello in five words."}]}')" | head -c 500; echo
say "3. chat with tools (the big question)"; curl -s -m 120 "${H[@]}" "$B/chat/completions" -d "$(json '{"model":"'"$M"'","messages":[{"role":"user","content":"What is the weather in Granger, Texas right now? Use the tool."}],"tools":[{"type":"function","function":{"name":"get_weather","description":"Current weather for a place","parameters":{"type":"object","properties":{"place":{"type":"string"}},"required":["place"]}}}],"tool_choice":"auto"}')" | head -c 900; echo
say "4. streaming"; curl -s -m 90 -N "${H[@]}" "$B/chat/completions" -d "$(json '{"model":"'"$M"'","stream":true,"messages":[{"role":"user","content":"Count to five."}]}')" | head -c 500; echo
say "5. text to speech"; curl -s -m 90 "${H[@]}" "$B/audio/speech" -d "$(json '{"model":"Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice","input":"Hello, I am Titan.","voice":"default"}')" -o /tmp/tiiny-tts.bin -w 'status %{http_code} bytes %{size_download} type %{content_type}\n'; file /tmp/tiiny-tts.bin 2>/dev/null | cut -c1-120
say "6. speech to text (set WAV=path to try)"; if [ -f "${WAV:-}" ]; then curl -s -m 90 -H "Authorization: Bearer $TIINY_KEY" "$B/audio/transcriptions" -F "file=@$WAV" -F model=default | head -c 300; echo; else echo "skipped"; fi
say "done"
