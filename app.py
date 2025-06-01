from flask import Flask, request, jsonify, render_template, send_file
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import os
import threading
import time

app = Flask(__name__)

# A simple dictionary to store automation status (for demonstration)
automation_status = {"message": "Idle", "progress": 0}

# Function to run the Selenium automation
# Now accepts username and password as arguments
def run_feedback_automation_task(username, password, captcha):
    global automation_status
    automation_status = {"message": "Starting automation...", "progress": 5}

    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode (no GUI)
    chrome_options.add_argument("--no-sandbox") # Required for some server environments like Render
    chrome_options.add_argument("--disable-dev-shm-usage") # Required for some server environments

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 300)

    try:
        automation_status = {"message": "Navigating to login page...", "progress": 10}
        driver.get("https://bitwebserver.bittechlearn.online:8084/Students/SubjectTeacher.aspx")
        print("Navigated to login page.")

        # --- Automated Login Steps ---
        # Replace 'username_id', 'password_id', 'login_button_id' with actual IDs from the website
        username_field = wait.until(EC.presence_of_element_located((By.ID, "TXTUSN")))
        username_field.send_keys(username)
        print("Entered username.")

        password_field = wait.until(EC.presence_of_element_located((By.ID, "TXTPASSWORD")))
        password_field.send_keys(password)
        print("Entered password.")
        
        wait.until(EC.element_to_be_clickable((By.ID, "BTN_GetCaptcha0"))).click()
        time.sleep(2)
        captcha_element = wait.until(EC.presence_of_element_located((By.ID, "Image2")))
        captcha_element.screenshot("static/captcha.png")
        
        captcha_field = wait.until(EC.presence_of_element_located((By.ID, "txtVerificationCode")))
        captcha_field.send_keys(captcha)

        login_button = wait.until(EC.element_to_be_clickable((By.ID, "btn_Login")))
        login_button.click()
        print("Clicked login button.")

        # Wait for an element that confirms successful login and redirection
        # Your current wait for 'btnPhase1Feedback' is a good indicator for this
        wait.until(EC.element_to_be_clickable((By.ID, "btnPhase1Feedback")))
        print("Login successful. Continuing automation...")
        automation_status = {"message": "Login successful. Starting Phase 1...", "progress": 30}
        # --- End Automated Login Steps ---


        def handle_phase(feedback_button_id, phase_name):
            global automation_status
            automation_status = {"message": f"Entering {phase_name}...", "progress": automation_status['progress'] + 5}
            driver.find_element(By.ID, feedback_button_id).click()

            pending_found_in_phase = True
            while pending_found_in_phase:
                pending_found_in_phase = False
                wait.until(EC.presence_of_element_located((By.ID, "gvCustomers")))
                rows = driver.find_elements(By.CSS_SELECTOR, "#gvCustomers tbody tr")

                for i in range(1, len(rows)):
                    rows = driver.find_elements(By.CSS_SELECTOR, "#gvCustomers tbody tr")
                    row = rows[i]
                    cells = row.find_elements(By.TAG_NAME, "td")
                    status = cells[3].text.strip()

                    if status == "Pending":
                        pending_found_in_phase = True
                        print(f"Found pending item in {phase_name}, clicking row {i}...")
                        automation_status = {"message": f"Processing pending item in {phase_name}...", "progress": min(90, automation_status['progress'] + 2)}
                        row.click()

                        wait.until(EC.url_contains("FeedBack.aspx"))
                        print("On FeedBack.aspx, filling ratings...")
                        automation_status = {"message": "Filling ratings...", "progress": min(90, automation_status['progress'] + 5)}

                        for j in range(1, 11):
                            radio_id = f"rdQ{j}_4"
                            radio = wait.until(EC.element_to_be_clickable((By.ID, radio_id)))
                            radio.click()

                        submit_btn = wait.until(EC.element_to_be_clickable((By.ID, "btn_submit")))
                        submit_btn.click()
                        print("Submitted feedback.")
                        automation_status = {"message": "Feedback submitted, navigating back...", "progress": min(90, automation_status['progress'] + 5)}

                        wait.until(EC.presence_of_element_located((By.ID, "HyperLink1")))
                        next_faculty = driver.find_element(By.ID, "HyperLink1")
                        next_faculty.click()

                        wait.until(EC.url_contains("SubjectTeacher.aspx"))
                        driver.find_element(By.ID, feedback_button_id).click()
                        print(f"Back to {phase_name} list, re-evaluating pending.")
                        break

                if not pending_found_in_phase:
                    print(f"No more pending feedbacks in {phase_name}.")
                    break

        handle_phase("btnPhase1Feedback", "Phase 1")

        automation_status = {"message": "Phase 1 complete. Proceeding to Phase 2...", "progress": 70}
        wait.until(EC.element_to_be_clickable((By.ID, "btnPhase2Feedback")))
        print("Phase 1 complete. Proceeding to Phase 2...")

        handle_phase("btnPhase2Feedback", "Phase 2")

        print("Automation complete!")
        automation_status = {"message": "Automation complete!", "progress": 100}
        return {"status": "success", "message": "Feedback automation completed."}

    except Exception as e:
        print(f"An error occurred: {e}")
        automation_status = {"message": f"Automation failed: {str(e)}", "progress": -1}
        return {"status": "error", "message": str(e)}
    finally:
        driver.quit()

@app.route('/start-automation', methods=['POST'])
def start_automation():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    captcha = data.get('captcha')

    if not username or not password:
        return jsonify({"status": "error", "message": "Username and password are required."}), 400

    threading.Thread(target=run_feedback_automation_task, args=(username, password, captcha)).start()
    return jsonify({"status": "initiated", "message": "Automation started in background."})

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify(automation_status)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/captcha')
def serve_captcha():
    return send_file("static/captcha.png", mimetype='image/png')

@app.route('/prepare-captcha', methods=['POST'])
def prepare_captcha():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"status": "error", "message": "Username and password are required."}), 400

    def capture_captcha():
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(driver, 60)
        try:
            driver.get("https://bitwebserver.bittechlearn.online:8084/Students/SubjectTeacher.aspx")
            wait.until(EC.presence_of_element_located((By.ID, "TXTUSN"))).send_keys(username)
            wait.until(EC.presence_of_element_located((By.ID, "TXTPASSWORD"))).send_keys(password)
            wait.until(EC.element_to_be_clickable((By.ID, "BTN_GetCaptcha0"))).click()
            time.sleep(2)
            captcha_element = wait.until(EC.presence_of_element_located((By.ID, "Image2")))
            captcha_element.screenshot("static/captcha.png")
        except Exception as e:
            print(f"CAPTCHA capture error: {e}")
        finally:
            driver.quit()

    threading.Thread(target=capture_captcha).start()
    return jsonify({"status": "preparing", "message": "CAPTCHA is being prepared, please wait a moment."})

if __name__ == '__main__':
    app.run()