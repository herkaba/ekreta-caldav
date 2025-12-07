import os, pickle, time, datetime, re
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
        pass

    def parse_html(self):
        kl = KretaLogin()
        kl.login_and_save_html()
        html = open("temp/orarend.html", "r", encoding="utf8").read()
        soup = BeautifulSoup(html, "html.parser")
        day_headers = soup.select(".fc-day-header")
        day_names = []
        for h in day_headers:
            lines = h.get_text("\n", strip=True).split("\n")
            day_names.append(lines[0])
        date_cells = soup.select(".fc-time-grid .fc-day")
        dates = [c.get("data-date") for c in date_cells]
        day_map = {}
        for index, (day, d) in enumerate(zip(day_names, dates)):
            y, m, dd = d.split("-")
            d_hu = f"{y}.{m}.{dd}."
            day_map[index] = {"day": day, "date": d_hu}
        events = []
        for col_index, column in enumerate(soup.select(".fc-time-grid .fc-event-container")):
            for ev in column.select(".fc-time-grid-event"):
                time_div = ev.select_one(".fc-time")
                title_div = ev.select_one(".fc-title")
                start = time_div.get("data-start")
                full_time = time_div.get("data-full")
                lines = title_div.decode_contents().strip().split("<br/>")
                lines = [BeautifulSoup(line, "html.parser").get_text() for line in lines]
                subject = lines[0]
                teacher = lines[1] if len(lines) > 1 else ""
                room = ""
                if "(" in subject and ")" in subject:
                    room = subject[subject.rfind("(")+1 : subject.rfind(")")]
                    subject = subject[:subject.rfind("(")].strip()
                event_data = {
                    "day": day_map[col_index]["day"],
                    "date": day_map[col_index]["date"],
                    "start": start,
                    "full_time": full_time,
                    "subject": subject,
                    "teacher": teacher,
                    "room": room
                }
                events.append(event_data)
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
        username_input = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input#UserName.form-control"))
        )
        username_input.send_keys(self.username)
        time.sleep(1)
        password_input = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input#Password.form-control"))
        )
        time.sleep(1)
        password_input.send_keys(self.password)
        login_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button#submit-btn"))
        )
        time.sleep(1)
        login_button.click()
        ellenorzo_btn = wait.until(
            EC.presence_of_element_located((By.XPATH, "//div[@onclick=\"BelepesKezelo.changeRole('Ellenorzo')\"]"))
        )
        time.sleep(1)
        driver.execute_script("arguments[0].scrollIntoView(true);", ellenorzo_btn)
        driver.execute_script("arguments[0].click();", ellenorzo_btn)
        try:
            kesobb_btn = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "ConfirmDashboardPopup7"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", kesobb_btn)
            driver.execute_script("arguments[0].click();", kesobb_btn)
            print("Később gomb megnyomva.")
        except TimeoutException:
            print("Később gomb nem található, továbblépünk.")
        cookies = driver.get_cookies()
        with open("temp/cookies.pkl", "wb") as f:
            pickle.dump(cookies, f)
        driver.get("https://verka.e-kreta.hu/Orarend/InformaciokOrarend")
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#Calendar .fc-event"))
            )
        except TimeoutException:
            print("Óra nem töltődött be időben, lehet, hogy nincs adat.")
        time.sleep(2)
        calendar_element = driver.find_element(By.ID, "Calendar")
        html_content = calendar_element.get_attribute("outerHTML")
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
        # Töröljük a régi eseményeket
        for e in self.calendar.events():
            e.delete()
        # Feltöltés
        for ev in events:
            try:
                start_parts = ev["date"].strip(".").split(".")
                start_year, start_month, start_day = map(int, start_parts)
                full_time = ev["full_time"]
                start_str, end_str = [t.strip() for t in full_time.split("-")]
                start_hour, start_minute = map(int, start_str.split(":"))
                end_hour, end_minute = map(int, end_str.split(":"))
                start_dt = datetime.datetime(start_year, start_month, start_day, start_hour, start_minute)
                end_dt = datetime.datetime(start_year, start_month, start_day, end_hour, end_minute)
                subject = ev["subject"]
                ical_event = Event()
                ical_event.add("summary", subject)
                ical_event.add("dtstart", start_dt)
                ical_event.add("dtend", end_dt)
                cal = Calendar()
                cal.add_component(ical_event)
                self.calendar.add_event(cal.to_ical())
            except Exception as e:
                print(f"Hiba az esemény feltöltésénél: {ev} -> {e}")
        print("Események feltöltve a CalDAV naptárba.")

# === Használat ===
gs = GetSchedule()
events = gs.parse_html()
uploader = CalUpload()
uploader.upload_events(events)
