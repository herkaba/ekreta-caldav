import hashlib
import logging
import os
import sys
import time
import warnings
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from bs4 import BeautifulSoup
from caldav import DAVClient
from dotenv import load_dotenv
from icalendar import Calendar, Event
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

load_dotenv()
warnings.filterwarnings("ignore", category=DeprecationWarning)

BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "temp"
HTML_FILE = TEMP_DIR / "orarend.html"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "sync.log"

KRETA_URL = "https://verka.e-kreta.hu/Orarend/InformaciokOrarend"
CHROME_PATH = "/opt/google/chrome/chrome"
CHROMEDRIVER_PATH = "/opt/chromedriver/installs/chromedriver-linux64/chromedriver"

try:
    from config import classes
except ImportError:
    classes = {}

TEMP_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("ekreta-sync")
logger.setLevel(logging.INFO)
logger.propagate = False

formatter = logging.Formatter(
    "%(asctime)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=5 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


class SyncStats:
    def __init__(self):
        self.calendar = "-"
        self.processed = 0
        self.added = 0
        self.updated = 0
        self.deleted = 0
        self.unchanged = 0
        self.errors = 0


class KretaLogin:
    def __init__(self):
        self.username = os.getenv("kreta_usr")
class KretaLogin:
    PROFILE_DIR = BASE_DIR / "chrome-profile"

    def __init__(self):
        self.username = os.getenv("kreta_usr")
        self.password = os.getenv("kreta_pwd")
        if not self.username or not self.password:
            raise RuntimeError("Hiányzik a kreta_usr vagy kreta_pwd az .env fájlból.")

    @staticmethod
    def setup_driver():
        if not os.path.isfile(CHROME_PATH) or not os.access(CHROME_PATH, os.X_OK):
            raise RuntimeError(f"Chrome nem futtatható: {CHROME_PATH}")
        if not os.path.isfile(CHROMEDRIVER_PATH) or not os.access(CHROMEDRIVER_PATH, os.X_OK):
            raise RuntimeError(f"ChromeDriver nem futtatható: {CHROMEDRIVER_PATH}")

        KretaLogin.PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        options = Options()
        options.binary_location = CHROME_PATH
        options.add_argument(f"--user-data-dir={KretaLogin.PROFILE_DIR}")
        options.add_argument("--profile-directory=Default")
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-notifications")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--remote-debugging-port=0")
        options.add_argument("--log-level=3")

        service = Service(
            executable_path=CHROMEDRIVER_PATH,
            log_output=os.devnull,
        )
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)
        return driver, WebDriverWait(driver, 20)

    @staticmethod
    def is_login_page(driver):
        return bool(
            driver.find_elements(By.ID, "UserName")
            or "idp.e-kreta.hu/account/login" in driver.current_url.lower()
        )

    @staticmethod
    def has_recaptcha(driver):
        return bool(
            driver.find_elements(By.CSS_SELECTOR, ".g-recaptcha")
            or driver.find_elements(By.ID, "ReCaptchaPublicKey")
        )

    def login_and_save_html(self):
        driver = None
        stage = "driver_start"

        try:
            driver, wait = self.setup_driver()

            stage = "open_kreta"
            driver.get(KRETA_URL)

            # Elsődlegesen a persistent Chrome-profilban eltárolt
            # autentikált KRÉTA sessiont használjuk.
            if self.is_login_page(driver):
                if self.has_recaptcha(driver):
                    raise RuntimeError(
                        "A KRÉTA session lejárt és reCAPTCHA szükséges. "
                        "Manuális bejelentkezés szükséges a chrome-profile használatával."
                    )

                stage = "username"
                username = wait.until(
                    EC.presence_of_element_located((By.ID, "UserName"))
                )
                password = wait.until(
                    EC.presence_of_element_located((By.ID, "Password"))
                )

                username.clear()
                username.send_keys(self.username)
                password.clear()
                password.send_keys(self.password)

                stage = "login_button"
                wait.until(
                    EC.element_to_be_clickable((By.ID, "submit-btn"))
                ).click()

                stage = "role_or_dashboard"
                try:
                    ellenorzo = WebDriverWait(driver, 12).until(
                        EC.presence_of_element_located(
                            (
                                By.XPATH,
                                "//div[@onclick=\"BelepesKezelo.changeRole('Ellenorzo')\"]",
                            )
                        )
                    )
                    driver.execute_script("arguments[0].click();", ellenorzo)
                except Exception:
                    if self.is_login_page(driver):
                        if self.has_recaptcha(driver):
                            raise RuntimeError(
                                "A KRÉTA reCAPTCHA validációt kér. "
                                "Manuális bejelentkezés szükséges."
                            )
                        raise RuntimeError(
                            "A KRÉTA bejelentkezés sikertelen."
                        )

            stage = "authenticated"
            if self.is_login_page(driver):
                raise RuntimeError(
                    "Nincs érvényes KRÉTA session."
                )

            stage = "popup"
            try:
                kesobb = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located(
                        (By.ID, "ConfirmDashboardPopup7")
                    )
                )
                driver.execute_script("arguments[0].click();", kesobb)
            except Exception:
                pass

            stage = "open_calendar"
            if "/Orarend/InformaciokOrarend" not in driver.current_url:
                driver.get(KRETA_URL)

            if self.is_login_page(driver):
                raise RuntimeError(
                    "Az órarend megnyitásakor a KRÉTA session már nem érvényes."
                )

            stage = "calendar_container"
            calendar = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".fullCalendar.fc")
                )
            )

            stage = "calendar_ajax_start"
            try:
                WebDriverWait(driver, 5).until(
                    lambda d: d.execute_script(
                        "return window.jQuery ? jQuery.active > 0 : false;"
                    )
                )
            except Exception:
                pass

            stage = "calendar_ajax_finish"
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script(
                    "return window.jQuery ? jQuery.active === 0 : true;"
                )
            )

            stage = "calendar_events"
            try:
                WebDriverWait(driver, 20).until(
                    lambda d: len(
                        d.find_elements(
                            By.CSS_SELECTOR,
                            ".fullCalendar .fc-event, "
                            ".fullCalendar .fc-time-grid-event",
                        )
                    ) > 0
                )
            except Exception as exc:
                html = calendar.get_attribute("innerHTML") or ""
                HTML_FILE.write_text(html, encoding="utf-8")
                (TEMP_DIR / "full_page.html").write_text(
                    driver.page_source,
                    encoding="utf-8",
                )
                driver.save_screenshot(
                    str(TEMP_DIR / "calendar_error.png")
                )

                event_count = len(
                    driver.find_elements(
                        By.CSS_SELECTOR,
                        ".fullCalendar .fc-event, "
                        ".fullCalendar .fc-time-grid-event",
                    )
                )
                jquery_active = driver.execute_script(
                    "return window.jQuery ? jQuery.active : -1;"
                )

                raise RuntimeError(
                    f"Az órarend betöltődött, de nincs esemény; "
                    f"events={event_count}; jquery_active={jquery_active}"
                ) from exc

            time.sleep(0.3)
            html = calendar.get_attribute("innerHTML") or ""

            if not html:
                raise RuntimeError("Az órarend HTML tartalma üres.")
            if "fc-" not in html:
                raise RuntimeError("Az órarend HTML tartalma nem megfelelő.")

            event_count = len(
                BeautifulSoup(html, "html.parser").select(
                    ".fc-event, .fc-time-grid-event"
                )
            )
            if event_count == 0:
                raise RuntimeError(
                    "Az órarend HTML mentésekor 0 esemény található."
                )

            HTML_FILE.write_text(html, encoding="utf-8")

        except Exception as exc:
            if driver is not None:
                try:
                    (TEMP_DIR / "error_page.html").write_text(
                        driver.page_source,
                        encoding="utf-8",
                    )
                except Exception:
                    pass

                try:
                    driver.save_screenshot(str(TEMP_DIR / "error.png"))
                except Exception:
                    pass

                try:
                    current_url = driver.current_url
                except Exception:
                    current_url = "-"
            else:
                current_url = "-"

            raise RuntimeError(
                f"kreta_stage={stage}; url={current_url}; "
                f"{type(exc).__name__}: {str(exc).strip()}"
            ) from exc

        finally:
            if driver is not None:
                driver.quit()


class GetSchedule:
    def parse_html(self):
        if not HTML_FILE.is_file():
            raise FileNotFoundError(f"Nem található: {HTML_FILE}")

        soup = BeautifulSoup(
            HTML_FILE.read_text(encoding="utf-8"),
            "html.parser",
        )

        raw_dates = []
        seen = set()

        for node in soup.select("[data-date]"):
            raw = node.get("data-date", "").strip()

            if not raw or raw in seen:
                continue

            try:
                date = datetime.strptime(
                    raw,
                    "%Y-%m-%d",
                ).date()
            except ValueError:
                continue

            seen.add(raw)
            raw_dates.append(date)

        dates = sorted(raw_dates)

        day_columns = soup.select(
            "td > .fc-event-container"
        )

        if not dates:
            raise RuntimeError(
                "A KRÉTA HTML-ben nem található használható data-date dátum."
            )

        if len(dates) < len(day_columns):
            raise RuntimeError(
                f"Kevés dátum található: "
                f"dátum={len(dates)}, oszlop={len(day_columns)}"
            )

        events = []

        for day_index, day_col in enumerate(
            day_columns
        ):
            current_date = dates[day_index]

            for element in day_col.select(
                ".fc-time-grid-event"
            ):
                time_el = element.select_one(
                    ".fc-time"
                )

                title_el = element.select_one(
                    ".fc-title"
                )

                if time_el is None or title_el is None:
                    continue

                full_time = time_el.get(
                    "data-full",
                    "",
                ).strip()

                if not full_time:
                    continue

                lines = title_el.get_text(
                    "\n",
                    strip=True,
                ).splitlines()

                events.append({
                    "date": current_date,
                    "full_time": full_time,
                    "subject": lines[0].strip() if lines else "",
                    "teacher": lines[1].strip() if len(lines) > 1 else "",
                    "room": lines[2].strip() if len(lines) > 2 else "",
                    "cancelled": "fc-textline-through" in (
                        element.get("class") or []
                    ),
                })

        return events


class CalUpload:
    UID_PREFIX = "ekreta-"

    def __init__(self):
        url = os.getenv("caldav_url")
        username = os.getenv("caldav_usr")
        password = os.getenv("caldav_pwd")

        if not url or not username or not password:
            raise RuntimeError(
                "Hiányzik a caldav_url, caldav_usr vagy caldav_pwd az .env fájlból."
            )

        self.client = DAVClient(
            url,
            username=username,
            password=password,
        )

        calendars = self.client.principal().calendars()

        if not calendars:
            raise RuntimeError(
                "Nincs elérhető CalDAV naptár."
            )

        requested_name = os.getenv("caldav_calendar", "").strip()
        if not requested_name:
            raise RuntimeError("Hiányzik a caldav_calendar a .env fájlból.")

        matches = [
            calendar for calendar in calendars
            if (calendar.get_display_name() or "").strip() == requested_name
        ]
        if len(matches) != 1:
            available = ", ".join(repr(c.get_display_name()) for c in calendars)
            raise RuntimeError(
                f"A megadott CalDAV naptár nem található vagy nem egyértelmű: "
                f"{requested_name!r}. Elérhető naptárak: {available}"
            )

        self.calendar = matches[0]
        self.name = requested_name

    @staticmethod
    def parse_times(event):
        value = (
            event["full_time"]
            .replace("–", "-")
            .replace("—", "-")
        )

        parts = value.split("-", 1)

        if len(parts) != 2:
            raise ValueError(
                f"Hibás időformátum: {event['full_time']}"
            )

        start_time = datetime.strptime(
            parts[0].strip(),
            "%H:%M",
        ).time()

        end_time = datetime.strptime(
            parts[1].strip(),
            "%H:%M",
        ).time()

        start = datetime.combine(
            event["date"],
            start_time,
        )

        end = datetime.combine(
            event["date"],
            end_time,
        )

        if end <= start:
            end += timedelta(days=1)

        return start, end

    @classmethod
    def get_uid(cls, event):
        start, _ = cls.parse_times(event)

        raw = (
            f"{event['date'].isoformat()}|"
            f"{start.strftime('%H:%M')}"
        )

        digest = hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()[:24]

        return (
            f"{cls.UID_PREFIX}"
            f"{digest}@kreta-caldav"
        )

    @classmethod
    def create_event(cls, event):
        start, end = cls.parse_times(event)

        subject = event["subject"]
        summary = classes.get(
            subject,
            subject,
        )

        room = (
            event["room"]
            .strip()
            .replace("(", "")
            .replace(")", "")
        )

        item = Event()

        item.add(
            "uid",
            cls.get_uid(event),
        )

        item.add(
            "summary",
            (
                f"[ELMARADT] {summary}"
                if event["cancelled"]
                else summary
            ),
        )

        item.add(
            "dtstart",
            start,
        )

        item.add(
            "dtend",
            end,
        )

        if event["cancelled"]:
            item.add(
                "status",
                "CANCELLED",
            )

        if room:
            item.add(
                "location",
                room,
            )

        item.add(
            "description",
            (
                f"Tantárgy: {subject}\n"
                f"Tanár: {event['teacher']}\n"
                f"Terem: {room}"
            ),
        )

        cal = Calendar()

        cal.add(
            "prodid",
            "-//KRÉTA CalDAV Sync//HU",
        )

        cal.add(
            "version",
            "2.0",
        )

        cal.add_component(item)

        return cal

    @staticmethod
    def event_signature(component):
        def value(name):
            field = component.get(name)

            if field is None:
                return ""

            if name in (
                "dtstart",
                "dtend",
            ):
                return field.dt.isoformat()

            return str(field)

        return (
            value("summary"),
            value("dtstart"),
            value("dtend"),
            value("location"),
            value("description"),
            value("status"),
        )

    def sync_events(self, events, stats):
        if not events:
            raise RuntimeError(
                "0 esemény érkezett, a naptárhoz nem nyúlok."
            )

        desired = {}

        for event in events:
            cal = self.create_event(event)

            component = next(
                c
                for c in cal.subcomponents
                if c.name == "VEVENT"
            )

            uid = str(
                component["uid"]
            )

            desired[uid] = (
                cal,
                self.event_signature(
                    component
                ),
            )

        existing = {}

        remote_events = self.calendar.events()

        for remote_event in remote_events:
            try:
                cal = Calendar.from_ical(
                    remote_event.data
                )

                component = next(
                    (
                        c
                        for c in cal.walk()
                        if c.name == "VEVENT"
                    ),
                    None,
                )

                if component is None:
                    continue

                uid_field = component.get(
                    "uid"
                )

                if uid_field is None:
                    continue

                uid = str(
                    uid_field
                )

                if not uid.startswith(
                    self.UID_PREFIX
                ):
                    continue

                existing[uid] = (
                    remote_event,
                    self.event_signature(
                        component
                    ),
                )

            except Exception:
                stats.errors += 1

        for uid, (
            cal,
            desired_signature,
        ) in desired.items():

            current = existing.get(uid)

            try:
                if current is None:
                    self.calendar.add_event(
                        cal.to_ical()
                    )

                    stats.added += 1
                    continue

                remote_event, current_signature = current

                if (
                    current_signature
                    == desired_signature
                ):
                    stats.unchanged += 1
                    continue

                remote_event.data = cal.to_ical()
                remote_event.save()

                stats.updated += 1

            except Exception:
                stats.errors += 1

        desired_uids = set(desired)
        managed_start = min(event["date"] for event in events)
        managed_end = max(event["date"] for event in events)

        for uid, (
            remote_event,
            _,
        ) in existing.items():

            if uid in desired_uids:
                continue

            try:
                remote_cal = Calendar.from_ical(remote_event.data)
                remote_component = next(
                    (c for c in remote_cal.walk() if c.name == "VEVENT"),
                    None,
                )

                if remote_component is None:
                    continue

                dtstart = remote_component.get("dtstart")

                if dtstart is None:
                    continue

                remote_date = dtstart.dt
                if isinstance(remote_date, datetime):
                    remote_date = remote_date.date()

                # Csak a KRÉTA által most betöltött hét/dátumtartomány
                # eseményeit kezeljük. Régebbi eseményhez nem nyúlunk.
                if not managed_start <= remote_date <= managed_end:
                    continue

                remote_event.delete()
                stats.deleted += 1

            except Exception:
                stats.errors += 1


def clean_message(exc):
    text = str(exc).replace(
        "\r",
        " ",
    ).replace(
        "\n",
        " ",
    ).strip()

    text = " ".join(
        text.split()
    )

    if text:
        return (
            f"{type(exc).__name__}: "
            f"{text[:500]}"
        )

    return type(exc).__name__


def main():
    started = time.monotonic()

    stats = SyncStats()

    status = "OK"
    error_message = ""
    stage = "init"

    try:
        stage = "kreta_login"
        KretaLogin().login_and_save_html()

        stage = "html_parse"
        events = GetSchedule().parse_html()

        stats.processed = len(events)

        if not events:
            raise RuntimeError(
                "A KRÉTA órarendből 0 eseményt sikerült kinyerni."
            )

        stage = "caldav_connect"
        uploader = CalUpload()

        stats.calendar = uploader.name

        stage = "caldav_sync"
        uploader.sync_events(
            events,
            stats,
        )

        if stats.errors:
            status = "WARNING"

    except Exception as exc:
        status = "ERROR"
        stats.errors += 1

        error_message = (
            f"stage={stage} | "
            f"{clean_message(exc)}"
        )

    elapsed = time.monotonic() - started

    message = (
        f"{status} | "
        f"naptar={stats.calendar} | "
        f"feldolgozva={stats.processed} | "
        f"uj={stats.added} | "
        f"frissitve={stats.updated} | "
        f"torolve={stats.deleted} | "
        f"valtozatlan={stats.unchanged} | "
        f"hiba={stats.errors} | "
        f"ido={elapsed:.2f}s"
    )

    if error_message:
        message += (
            f" | uzenet={error_message}"
        )

    logger.info(message)

    return (
        0
        if status == "OK"
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())
