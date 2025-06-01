from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

options = Options()
# options.add_argument("--headless") # Make sure this is commented out
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36")

try:
    driver = webdriver.Chrome(options=options)
    driver.get("https://www.google.com")
    print("Browser launched successfully!")
    time.sleep(5) # Keep it open for 5 seconds
except Exception as e:
    print(f"Failed to launch browser: {e}")
finally:
    if 'driver' in locals() and driver:
        driver.quit()