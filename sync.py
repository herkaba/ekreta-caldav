import os, pickle, time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from caldav import DAVClient
from icalendar import Event, Calendar
from dotenv import load_dotenv
from rich import print


class GetSchedule:
    def __init__(self):
        today = datetime.today()
        week_start_date = (today - timedelta(days=today.weekday())).strftime("%Y.%m.%d")
        self.week_start = datetime.strptime(week_start_date, "%Y.%m.%d").date()

    def parse_html(self):
        with open("temp/orarend.html", "r", encoding="utf-8") as f:
            html = f.read()
        soup = BeautifulSoup(html, "html.parser")
        events = []

        day_columns = soup.select("td > .fc-event-container")

        for day_index, day_col in enumerate(day_columns):
            current_date = self.week_start + timedelta(days=day_index)

            for ev in day_col.select(".fc-time-grid-event"):
                time_el = ev.select_one(".fc-time")
                title_el = ev.select_one(".fc-title")

                if not time_el or not title_el:
                    continue

                start_time = time_el.get("data-start", "").strip()
                full_time = time_el.get("data-full", "").strip()

                lines = title_el.get_text("\n", strip=True).split("\n")

                subject = lines[0] if len(lines) > 0 else ""
                teacher = lines[1] if len(lines) > 1 else ""
                room = lines[2] if len(lines) > 2 else ""

                cancelled = "fc-textline-through" in ev.get("class", [])

                events.append({
                    "date": current_date.isoformat().replace("-", ".") + ".",
                    "weekday_index": day_index + 1,
                    "start_time": start_time,
                    "full_time": full_time,
                    "subject": subject,
                    "teacher": teacher,
                    "room": room,
                    "cancelled": cancelled
                })

        return events
    
class KretaLogin:
    def __init__(self):
        load_dotenv()
        self.username = os.getenv("kreta_usr")
        self.password = os.getenv("kreta_pwd")
        os.makedirs("temp", exist_ok=True)
    def setup_driver(self):
        service = Service("/opt/chromedriver/installs/chromedriver-linux64/chromedriver")
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 15)
        return driver, wait
    def login_and_save_html(self):
        driver, wait = self.setup_driver()
        driver.get("https://verka.e-kreta.hu/Orarend/InformaciokOrarend")
        username_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input#UserName.form-control")))
        username_input.send_keys(self.username)
        time.sleep(1)
        password_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input#Password.form-control")))
        password_input.send_keys(self.password)
        time.sleep(1)
        login_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button#submit-btn")))
        login_button.click()
        ellenorzo_btn = wait.until(
            EC.presence_of_element_located((By.XPATH, "//div[@onclick=\"BelepesKezelo.changeRole('Ellenorzo')\"]"))
        )
        driver.execute_script("arguments[0].click();", ellenorzo_btn)
        try:
            kesobb_btn = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "ConfirmDashboardPopup7"))
            )
            driver.execute_script("arguments[0].click();", kesobb_btn)
            print("Később gomb megnyomva.")
        except TimeoutException:
            print("Később gomb nem található.")
        cookies = driver.get_cookies()
        with open("temp/cookies.pkl", "wb") as f:
            pickle.dump(cookies, f)
        driver.get("https://verka.e-kreta.hu/Orarend/InformaciokOrarend")
        try:
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#Calendar .fc-event")))
        except TimeoutException:
            print("Óra nem töltődött be időben.")
        time.sleep(2)
        calendar_element = driver.find_element(By.CLASS_NAME, "fullCalendar fc fc-ltr fc-unthemed")
        html_content = calendar_element.get_attribute("innerHTML")
        with open("temp/orarend.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        print("HTML mentve: temp/orarend.html")
        os.remove("temp/cookies.pkl")
        driver.quit()

class CalUpload:
    def __init__(self):
        load_dotenv()
        self.url = os.getenv("caldav_url")
        self.username = os.getenv("caldav_usr")
        self.password = os.getenv("caldav_pwd")
        self.client = DAVClient(self.url, username=self.username, password=self.password)
        self.principal = self.client.principal()
        self.calendars = self.principal.calendars()
        if not self.calendars:
            raise Exception("Nincs elérhető naptár!")
        self.calendar = self.calendars[0]
        print(f"Csatlakozva a naptárhoz: {self.calendar.name}")
    def upload_events(self, events):
        for e in self.calendar.events():
            e.delete()
        added_count = 0
        for ev in events:
            try:
                start_year, start_month, start_day = map(int, ev["date"].strip(".").split("."))
                times = ev["full_time"].replace("–", "-").split("-")  # cseréljük az esetleges hosszú kötőjelet simára
                if len(times) != 2:
                    print(f"[red]Hibás idő formátum: {ev['full_time']}[/red]")
                    continue
                start_str, end_str = [t.strip() for t in times]
                start_hour, start_minute = map(int, start_str.split(":"))
                end_hour, end_minute = map(int, end_str.split(":"))
                start_dt = datetime(start_year, start_month, start_day, start_hour, start_minute)
                end_dt = datetime(start_year, start_month, start_day, end_hour, end_minute)
                from config import classes
                ical_event = Event()
                if ev["cancelled"]:
                    print(f"[yellow]Esemény törölt: {ev}[/yellow]")
                    ical_event.add("status", "canceled")
                    ical_event.add("summary", "[ELMARADT] " + classes.get(ev["subject"]))
                else:
                    ical_event.add("summary", classes.get(ev["subject"]))
                ical_event.add("dtstart", start_dt)
                ical_event.add("dtend", end_dt)
                ical_event.add("description", f"Tantárgy: {ev['subject']}\nTanár: {ev['teacher']}\nTerem: {ev['room'].strip().replace('(', '').replace(')', '')}")
                cal = Calendar()
                cal.add_component(ical_event)
                self.calendar.add_event(cal.to_ical())
                added_count += 1
            except Exception as e:
                print(f"[red]Hiba az esemény feltöltésénél: {ev} -> {e}[/red]")
        print(f"Események feltöltve: {added_count} darab.")

gs = GetSchedule()
events = gs.parse_html()
uploader = CalUpload()
uploader.upload_events(events)