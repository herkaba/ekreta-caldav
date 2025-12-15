# ekreta-caldav

Sync e‑Kréta weekly timetable to a CalDAV calendar.

This small utility logs into the e‑Kréta portal, downloads the weekly timetable (HTML), parses lessons, and uploads them as VEVENTs to a CalDAV calendar (replacing existing events).

**Requirements**
- **Python:** `3.9+`
- **Browser:** Google Chrome or Chromium
- **Chromedriver:** matching your browser version (the code uses `/opt/chromedriver/installs/chromedriver-linux64/chromedriver` by default)
- **Python packages:**
  - Install with: `pip install beautifulsoup4 selenium python-dotenv caldav icalendar rich`

**Quick Start**

1. Clone the repository and create a virtual environment (recommended):

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt || pip install beautifulsoup4 selenium python-dotenv caldav icalendar rich
    ```

2. Create a `.env` file in the project root with your credentials (example below).

3. Ensure Chromedriver is installed and its path matches the one in `sync.py` (or update the path in `KretaLogin.setup_driver`).

4. Run once to sync:

    ```bash
    python3 sync.py
    # or
    ./run_sync.sh
    ```

**Environment (.env) example**

Create a `.env` file in the project root containing:

```
kreta_usr=YOUR_KRETA_USERNAME
kreta_pwd=YOUR_KRETA_PASSWORD

caldav_url=https://your-caldav.example.com
caldav_usr=YOUR_CALDAV_USERNAME
caldav_pwd=YOUR_CALDAV_PASSWORD
```

Do NOT commit your `.env` file — it contains secrets.

Create a `config.py` if you want to rewrite the subject names in your case:

```
classes = {
    "write the original subject": "mapped subject",
}
```

**How it works (high level)**
- `KretaLogin` (Selenium): logs into e‑Kréta, switches role if needed, saves the calendar HTML to `temp/orarend.html`.
- `GetSchedule.parse_html`: parses `temp/orarend.html` and returns a list of events (date, start/end, subject, teacher, room).
- `CalUpload`: connects to the first available CalDAV calendar, deletes existing events, and uploads parsed lessons as iCalendar VEVENTs.

**Files of interest**
- `sync.py` — main script (login, parse, upload).
- `run_sync.sh` — wrapper script to run `sync.py` (make executable with `chmod +x run_sync.sh`).
- `temp/` — runtime temp files (e.g. `orarend.html`).

**Automation / Cron**
Add a cron job (example runs daily at 03:00):

```
0 3 * * * /path/to/venv/bin/python /home/USER/ekreta-caldav/sync.py
```

If you use Conda, activate the environment inside `run_sync.sh` before running `python`.

**Troubleshooting & notes**
- If Chromedriver fails: ensure your browser and Chromedriver versions match and that the binary is executable.
- The chromedriver path is hardcoded; change the path in `KretaLogin.setup_driver()` if needed.
- If e‑Kréta changes their HTML layout, `GetSchedule.parse_html()` may need updates.
- `temp/orarend.html` is overwritten each run; cookies are handled temporarily.

**Security**
- Keep `.env` out of version control. Add secrets to your CI/CD secret manager if automating remotely.

**License**
Summary: This project is licensed under the MIT License.
File: See LICENSE for the full text.
<img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT">
