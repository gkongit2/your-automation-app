from flask import Flask, request, jsonify, render_template
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import os
import threading
import time # For simulating work/delays

app = Flask(__name__)

# A simple dictionary to store automation status (for demonstration)
automation_status = {"message": "Idle", "progress": 0}

# Function to run the Selenium automation
def run_feedback_automation_task():
    global automation_status
    automation_status = {"message": "Starting automation...", "progress": 5}

    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode (no GUI)
    chrome_options.add_argument("--no-sandbox") # Required for some server environments like Render
    chrome_options.add_argument("--disable-dev-shm-usage") # Required for some server environments

    # Path to chromedriver executable (will be handled by Render's setup later)
    # For local testing, you might need to specify the path:
    # driver = webdriver.Chrome(executable_path="/path/to/chromedriver", options=chrome_options)
    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 300) # Increased wait time as network might be slower

    try:
        automation_status = {"message": "Navigating to login page...", "progress": 10}
        driver.get("https://bitwebserver.bittechlearn.online:8084/Students/SubjectTeacher.aspx")
        print("Waiting for login...")

        # !!! IMPORTANT: You will need to manually log in for this to proceed,
        # or implement automated login if you have credentials.
        # This script assumes manual login for now.
        automation_status = {"message": "Please log in manually in the opened browser window (if running locally) or ensure previous login for server automation.", "progress": 20}
        wait.until(EC.element_to_be_clickable((By.ID, "btnPhase1Feedback")))
        print("Login detected. Continuing automation...")
        automation_status = {"message": "Login detected. Starting Phase 1...", "progress": 30}

        def handle_phase(feedback_button_id, phase_name):
            global automation_status # To modify the outer scope's automation_status
            automation_status = {"message": f"Entering {phase_name}...", "progress": automation_status['progress'] + 5}
            driver.find_element(By.ID, feedback_button_id).click()

            pending_found_in_phase = True
            while pending_found_in_phase:
                pending_found_in_phase = False # Reset for each iteration
                wait.until(EC.presence_of_element_located((By.ID, "gvCustomers")))
                rows = driver.find_elements(By.CSS_SELECTOR, "#gvCustomers tbody tr")

                for i in range(1, len(rows)):
                    # Re-find rows inside the loop as the DOM might change after a click
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
                        # Click the phase button again to refresh the list of pending items
                        driver.find_element(By.ID, feedback_button_id).click()
                        print(f"Back to {phase_name} list, re-evaluating pending.")
                        break # Break and re-evaluate the table as it might have changed

                if not pending_found_in_phase:
                    print(f"No more pending feedbacks in {phase_name}.")
                    break # Exit the while loop if no pending found

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
        automation_status = {"message": f"Automation failed: {str(e)}", "progress": -1} # Use -1 for error state
        return {"status": "error", "message": str(e)}
    finally:
        driver.quit() # Ensure the browser is closed

# Endpoint to start the automation
@app.route('/start-automation', methods=['POST'])
def start_automation():
    # To prevent multiple concurrent runs, you might want to add a lock
    # For simplicity here, we'll just start a new thread.
    # In a real production app, consider task queues like Celery.
    threading.Thread(target=run_feedback_automation_task).start()
    return jsonify({"status": "initiated", "message": "Automation started in background."})

# Endpoint to get the current status
@app.route('/status', methods=['GET'])
def get_status():
    return jsonify(automation_status)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    # When running locally, Flask runs in a single thread by default.
    # Selenium operations can be long-running and block the main thread.
    # For local development, running with debug=True (which enables reloader)
    # can sometimes cause issues with threads.
    # For simple testing, you can use app.run() directly.
    # For deployment, Gunicorn will handle concurrency.
    # app.run(debug=True)
    app.run()