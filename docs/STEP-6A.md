# Step 6a: no subprocess anywhere in Lite

tiinyapp.farm's submission scanner refuses any archive that imports subprocess (the farm has no
"shell" permission by design). lite/server.py:918 imports subprocess and spawns a child for the
cold-start measurement in --selfcheck (and possibly the boot probe). Replace it: measure cold
start by constructing the app and binding the server in a thread inside the same process (time
from import to the first successful GET /api/health on a spare port), then shut it down. Remove
every subprocess and os.system use from lite/ (grep to prove zero). Keep the selfcheck's printed
numbers and the budget assertions. `python3 -m unittest` green. Bump lite/VERSION by one on the
last number. Append "Step 6a" to docs/REPORT.md. No browser or GUI. Commit is not possible from
your sandbox.
