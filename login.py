import os
import pickle
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from dotenv import load_dotenv


class KretaLogin:
    def __init__(self):
        load_dotenv()
        self.username = os.getenv("USERNAME")
        self.password = os.getenv("PASSWORD")
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
    def login(self):
        driver, wait = self.setup_driver()
        driver.get("https://verka.e-kreta.hu/Orarend/InformaciokOrarend")
        username_input = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input#UserName.form-control"))
        )
        username_input.send_keys(self.username)
        password_input = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input#Password.form-control"))
        )
        password_input.send_keys(self.password)
        login_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button#submit-btn"))
        )
        login_button.click()
        ellenorzo_btn = wait.until(
            EC.presence_of_element_located((By.XPATH, "//div[@onclick=\"BelepesKezelo.changeRole('Ellenorzo')\"]"))
        )
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
        print("Sütik elmentve: cookies.pkl")
        driver.get("https://verka.e-kreta.hu/Orarend/InformaciokOrarend")
        html_content = driver.page_source
        with open("temp/orarend.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        print("HTML mentve: temp/orarend.html")
        os.remove("temp/cookies.pkl")
        driver.quit()

if __name__ == "__main__":
    kreta_login = KretaLogin()
    kreta_login.login()