#!/usr/bin/env bash
# Step 0: ten minutes with the Tiiny on the LAN. Answers the three questions everything else
# depends on. Usage: TIINY_IP=192.168.x.y TIINY_KEY="$(tiiny auth key)" bash scripts/probe-device.sh
# Never paste the key into a chat; this script prints only status codes and short answers.
set -u
: "${TIINY_IP:?set TIINY_IP to the device address}"; : "${TIINY_KEY:?set TIINY_KEY from: tiiny auth key}"
B="http://$TIINY_IP:8800/v1"; H=(-H "Authorization: Bearer $TIINY_KEY" -H "Content-Type: application/json")
say() { printf '\n== %s\n' "$*"; }
say "1. models"; curl -s -m 15 "${H[@]}" "$B/models" | head -c 600; echo
say "2. chat, plain"; curl -s -m 60 "${H[@]}" "$B/chat/completions" -d '{"model":"default","messages":[{"role":"user","content":"Say hello in five words."}]}' | head -c 400; echo
say "3. chat with tools (the big question)"; curl -s -m 60 "${H[@]}" "$B/chat/completions" -d '{"model":"default","messages":[{"role":"user","content":"What is the weather in Granger, Texas right now? Use the tool."}],"tools":[{"type":"function","function":{"name":"get_weather","description":"Current weather for a place","parameters":{"type":"object","properties":{"place":{"type":"string"}},"required":["place"]}}}],"tool_choice":"auto"}' | head -c 800; echo
say "4. streaming"; curl -s -m 60 -N "${H[@]}" "$B/chat/completions" -d '{"model":"default","stream":true,"messages":[{"role":"user","content":"Count to five."}]}' | head -c 400; echo
say "5. text to speech"; curl -s -m 60 "${H[@]}" "$B/audio/speech" -d '{"model":"default","input":"Hello, I am Titan.","voice":"default"}' -o /tmp/tiiny-tts.mp3 -w 'status %{http_code} bytes %{size_download}\n'
say "6. speech to text (needs a wav; skip if none)"; [ -f "${WAV:-}" ] && curl -s -m 60 -H "Authorization: Bearer $TIINY_KEY" "$B/audio/transcriptions" -F "file=@$WAV" -F model=default | head -c 300; echo
say "done. Paste this whole output (it holds no key) into the chat."
