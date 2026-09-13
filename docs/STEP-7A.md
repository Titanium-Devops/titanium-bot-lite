# Step 7a: the Model section finishes SPEC step 2

SPEC.md's delivery step 2 is the only numbered step with no brief and no section in
docs/REPORT.md. `POST /api/model` refuses start and stop with 501 at lite/server.py:1170 and
refuses any other connection with 501 at :1174, and Settings > Model draws "Model controls: On
your device" and "Connecting another computer or a cloud model is not available yet." An owner
whose chat model is stopped is sent to TiinyOS to fix it, which is the failure the README warns
about on its front page.

Read SPEC.md (the Model bullet under Shape, and delivery step 2), docs/console-pieces.md section
11 routes 6 and 7, docs/tiiny-platform.md sections 2 and 6, lite/device.py (how the address and
the gateway port are found), lite/voice.py (`lifecycle` already posts to
`/api/v1/models/<model>/<action>` on the device root with the `Host: p8800.api.tiiny` rule for
firmware 1.0, and holds the lane), and lite/server.py around the `/api/model` and `/api/models`
handlers.

1. Start and stop. `POST /api/model {"action":"start"|"stop","id"}` runs the device's own model
   lifecycle. Move `Voice.lifecycle` somewhere both the voice turn and this route can call it
   rather than reaching across into `app.voice`; it stays one implementation with the lane held
   and the Host rule intact. Refuse stopping the model Titan is answering on, in words, rather
   than stopping it and failing the next turn. A device that refuses the start says so in its own
   words, not ours.
2. Real running state. `GET /api/models` marks `running` by comparing the row id against
   `device.resolved_model`, which is the model Lite picked, not the model the device has loaded.
   Read the device's own loaded rows and report that. Verify against the attached unit which field
   carries it before writing the shape down.
3. Another computer. `POST /api/model {"action":"use","baseUrl","model","apiKey"}` saves an
   OpenAI-compatible endpoint on the LAN. The key goes to `keys.json` at 0600 and is never echoed
   in any answer and never reaches the page. `GET /api/models` fills its `lan` list and `live`
   names the source. Settings > Model replaces the "not available yet" line with an address, a
   model and a masked key box, and the masked box is the only place a credential is ever typed,
   which is the rule the seeded never-ask pack already states.
4. A cloud key is the same route with a cloud address, so it needs no third shape. Say in the
   Model section which one is in use and let the owner switch back to the device in one press.
5. Switching while a turn is queued must not strand the queue: the change takes effect on the next
   turn, and the one in flight finishes on the endpoint it started on.

Tests: the lifecycle route against a fake device that answers start, stop and a refusal; the
running flag read off loaded rows; the endpoint switch persisting across a restart; the key
absent from every response body, from `/api/state`, from `/api/settings` and from the log; the
refusal to stop the model in use. `python3 -m unittest` green. Bump lite/VERSION by one on the
last number. Append a "Step 7a" section to docs/REPORT.md.

One warning from the audit that produced this brief: the device answers `401 auth_failed` without
a key, and the audit had no key, so none of the device protocol above was exercised against real
firmware. Run it against the attached unit before writing any of it down as measured.
