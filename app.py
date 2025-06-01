from flask import Flask, request, jsonify, render_template, send_file, make_response
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException, NoSuchElementException, NoAlertPresentException
import os
import threading
import time
import queue # Import queue for inter-thread communication
import logging # Import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Global state for automation status and thread communication
automation_status = {"message": "Idle", "progress": 0, "captcha_ready": False} # Initialize captcha_ready
# Queue to pass CAPTCHA solution from Flask route to the Selenium thread
captcha_solution_queue = queue.Queue()
# Event to signal the Selenium thread to wait for CAPTCHA input
captcha_ready_event = threading.Event()
# Event to signal the Selenium thread that CAPTCHA input has been received
captcha_submitted_event = threading.Event()

# This will hold the WebDriver instance for the active session
current_driver_instance = None

# Function to run the Selenium automation
def run_feedback_automation_task(username, password):
    global automation_status, current_driver_instance
    automation_status = {"message": "Starting automation...", "progress": 5, "captcha_ready": False}

    chrome_options = Options()
    chrome_options.add_argument("--headless") # Keep headless for Render deployment
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36")

    driver = None
    captcha_image_path = os.path.join(app.root_path, "static", "captcha.png")

    try:
        driver = webdriver.Chrome(options=chrome_options)
        current_driver_instance = driver # Store the driver instance globally
        wait = WebDriverWait(driver, 60) # Increased wait time

        logging.info("Navigating to login page.")
        automation_status = {"message": "Navigating to login page...", "progress": 10, "captcha_ready": False}
        driver.get("https://bitwebserver.bittechlearn.online:8084/Students/SubjectTeacher.aspx")
        
        # Clear any existing captcha.png in case the server didn't restart
        if os.path.exists(captcha_image_path):
            try:
                os.remove(captcha_image_path)
                logging.info("Removed old captcha.png before new screenshot.")
            except Exception as e:
                logging.warning(f"Could not remove old captcha.png: {e}")

        # --- Click "Click To Get Captcha" ---
        try:
            get_captcha_button = wait.until(EC.element_to_be_clickable((By.ID, "BTN_GetCaptcha0")))
            get_captcha_button.click()
            logging.info("Clicked 'Click To Get Captcha' button.")
            time.sleep(2) # Give a moment for the new image to load and JS to update
        except TimeoutException:
            logging.warning("Warning: 'Click To Get Captcha' button not found or not clickable.")
            # Continue without clicking if the button isn't there, might mean captcha is static

        # Wait for the CAPTCHA image element to be present and visible *after* the click
        captcha_element = wait.until(EC.presence_of_element_located((By.ID, "Image2")))
        # Add condition to wait until the src attribute is not just "StudentLogin.aspx"
        wait.until(lambda d: captcha_element.get_attribute("src") not in ["", "StudentLogin.aspx"])
        wait.until(EC.visibility_of(captcha_element))
        logging.info("Captcha image element is present and visible with a valid source.")

        # Take screenshot of the CAPTCHA from THIS live session
        captcha_element.screenshot(captcha_image_path)
        logging.info("CAPTCHA image captured for user input.")
        
        # Signal the frontend that CAPTCHA is ready for input
        automation_status = {"message": "CAPTCHA ready for input. Please solve.", "progress": 20, "captcha_ready": True}
        captcha_ready_event.set() # Set the event to indicate CAPTCHA is ready

        # --- PAUSE EXECUTION AND WAIT FOR USER CAPTCHA INPUT ---
        logging.info("Automation paused, waiting for user to solve CAPTCHA...")
        # Wait indefinitely for the captcha_submitted_event to be set.
        # The frontend should handle timeouts or user cancellation.
        captcha_submitted_event.wait() 
        
        # Get the CAPTCHA solution from the queue
        solved_captcha = captcha_solution_queue.get(timeout=10) # Get solution, wait a bit
        captcha_solution_queue.task_done() # Mark task as done
        logging.info(f"Received CAPTCHA solution from user. Length: {len(solved_captcha)}") # Log length, not value

        # Reset the events immediately after getting the input
        captcha_ready_event.clear()
        captcha_submitted_event.clear()
        automation_status["captcha_ready"] = False # Update status immediately

        # --- IMPORTANT: Re-find elements after the pause ---
        # The page might have refreshed or elements might have become stale during the user interaction time.
        # This prevents StaleElementReferenceException.
        logging.info("Re-finding elements after CAPTCHA input...")
        captcha_field = wait.until(EC.presence_of_element_located((By.ID, "txtVerificationCode")))
        username_field = wait.until(EC.presence_of_element_located((By.ID, "TXTUSN")))
        password_field = wait.until(EC.presence_of_element_located((By.ID, "TXTPASSWORD")))
        login_button = wait.until(EC.element_to_be_clickable((By.ID, "btn_Login")))

        # --- Fill the fields with the provided solution and credentials ---
        captcha_field.send_keys(solved_captcha) # Use the received solution
        logging.info("Filled CAPTCHA field.")

        username_field.send_keys(username)
        logging.info("Filled username field.")

        password_field.send_keys(password)
        logging.info("Filled password field.")
        
        time.sleep(2) # Allow client-side scripts to process the inputs

        login_button.click()
        logging.info("Clicked login button. Waiting for redirection or error indication...")
        
        # --- Login Verification and Subsequent Automation Steps ---
        try:
            wait.until(EC.url_contains("StudentsCorner.aspx"))
            logging.info("Login successful. Redirected to StudentsCorner.aspx.")
            automation_status = {"message": "Login successful.", "progress": 30, "captcha_ready": False}
            # Clean up the captcha.png after successful login
            if os.path.exists(captcha_image_path):
                try:
                    os.remove(captcha_image_path)
                    logging.info("Deleted used captcha.png after successful login.")
                except Exception as e:
                    logging.warning(f"Could not delete used captcha.png: {e}")
        except TimeoutException:
            logging.info("Timeout waiting for redirection after login. Checking for alternative failure signs...")
            # Try to handle immediate alerts first
            try:
                alert = driver.switch_to.alert
                alert_text = alert.text
                logging.error(f"Alert found after login attempt: {alert_text}")
                alert.accept() # Accept the alert to dismiss it
                automation_status = {"message": f"Login failed: Alert - {alert_text}", "progress": -1, "captcha_ready": False}
                return {"status": "error", "message": f"Login failed: {alert_text}"}
            except NoAlertPresentException:
                logging.info("No immediate alert found. Checking for error messages on the page.")
                
                error_message = None
                try:
                    error_elements_ids = ["lblMsg", "ErrorMessage", "ctl00_ContentPlaceHolder1_lblMessage"]
                    for eid in error_elements_ids:
                        try:
                            error_el = wait.until(EC.visibility_of_element_located((By.ID, eid)))
                            if error_el.text.strip():
                                error_message = error_el.text.strip()
                                break
                        except TimeoutException:
                            pass

                    if error_message:
                        logging.error(f"Found on-page error message: {error_message}")
                        automation_status = {"message": f"Login failed: On-page error - {error_message}", "progress": -1, "captcha_ready": False}
                        return {"status": "error", "message": f"Login failed: {error_message}"}
                    else:
                        logging.warning("No specific error message element found on the page.")

                except Exception as e:
                    logging.error(f"Error checking for on-page error messages: {e}")

                screenshot_path = os.path.join(app.root_path, "static", "login_failure_screenshot.png")
                driver.save_screenshot(screenshot_path)
                logging.error(f"Login failed, no redirect and no immediate alert/error message. Screenshot saved to {screenshot_path}")
                automation_status = {"message": f"Login failed: No redirect or alert. See screenshot.", "progress": -1, "captcha_ready": False}
                return {"status": "error", "message": "Login failed: Check screenshot for details."}
        
        # ✅ Click the 'Feedback' tab if login succeeded
        feedback_link = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//a[contains(@href, "SubjectTeacher.aspx") and contains(text(), "Feedback")]'))
        )
        feedback_link.click()
        logging.info("Navigated to Feedback page.")
        automation_status = {"message": "Successfully navigated to Feedback page.", "progress": 40, "captcha_ready": False}
        
        wait.until(EC.element_to_be_clickable((By.ID, "btnPhase1Feedback")))
        logging.info("On SubjectTeacher.aspx. Starting Phase 1...")
        automation_status = {"message": "On SubjectTeacher.aspx. Starting Phase 1...", "progress": 50, "captcha_ready": False}

        def handle_phase(feedback_button_id, phase_name):
            global automation_status # Use nonlocal for nested function
            automation_status = {"message": f"Entering {phase_name}...", "progress": automation_status['progress'] + 5, "captcha_ready": False}
            wait.until(EC.element_to_be_clickable((By.ID, feedback_button_id))).click()

            pending_found_in_phase = True
            while pending_found_in_phase:
                pending_found_in_phase = False
                wait.until(EC.presence_of_element_located((By.ID, "gvCustomers")))
                rows = driver.find_elements(By.CSS_SELECTOR, "#gvCustomers tbody tr")

                if len(rows) <= 1:
                    logging.info(f"No pending items found in {phase_name} table (only header or empty).")
                    break

                for i in range(1, len(rows)):
                    rows = driver.find_elements(By.CSS_SELECTOR, "#gvCustomers tbody tr") # Re-find rows
                    row = rows[i]
                    cells = row.find_elements(By.TAG_NAME, "td")
                    
                    if len(cells) > 3:
                        status = cells[3].text.strip()
                    else:
                        logging.warning(f"Row {i} in {phase_name} has fewer than 4 cells. Skipping.")
                        continue

                    if status == "Pending":
                        pending_found_in_phase = True
                        logging.info(f"Found pending item in {phase_name}, clicking row {i}...")
                        automation_status = {"message": f"Processing pending item in {phase_name}...", "progress": min(90, automation_status['progress'] + 2), "captcha_ready": False}
                        row.click()

                        wait.until(EC.url_contains("FeedBack.aspx"))
                        logging.info("On FeedBack.aspx, filling ratings...")
                        automation_status = {"message": "Filling ratings...", "progress": min(90, automation_status['progress'] + 5), "captcha_ready": False}

                        for j in range(1, 11):
                            radio_id = f"rdQ{j}_4"
                            try:
                                radio = wait.until(EC.element_to_be_clickable((By.ID, radio_id)))
                                radio.click()
                                logging.info(f"Clicked radio button {radio_id}")
                            except TimeoutException:
                                logging.warning(f"Radio button {radio_id} not found or not clickable. Skipping.")
                                continue

                        submit_btn = wait.until(EC.element_to_be_clickable((By.ID, "btn_submit")))
                        submit_btn.click()
                        logging.info("Submitted feedback.")
                        automation_status = {"message": "Feedback submitted, navigating back...", "progress": min(90, automation_status['progress'] + 5), "captcha_ready": False}

                        wait.until(EC.presence_of_element_located((By.ID, "HyperLink1")))
                        next_faculty = driver.find_element(By.ID, "HyperLink1")
                        next_faculty.click()

                        wait.until(EC.url_contains("SubjectTeacher.aspx"))
                        # Re-click the phase button to refresh the list and look for more pending items
                        wait.until(EC.element_to_be_clickable((By.ID, feedback_button_id))).click()
                        logging.info(f"Back to {phase_name} list, re-evaluating pending.")
                        break

                if not pending_found_in_phase:
                    logging.info(f"No more pending feedbacks in {phase_name}.")
                    break

        handle_phase("btnPhase1Feedback", "Phase 1")

        automation_status = {"message": "Phase 1 complete. Proceeding to Phase 2...", "progress": 70, "captcha_ready": False}
        wait.until(EC.element_to_be_clickable((By.ID, "btnPhase2Feedback")))
        logging.info("Phase 1 complete. Proceeding to Phase 2...")

        handle_phase("btnPhase2Feedback", "Phase 2")

        logging.info("Automation complete!")
        automation_status = {"message": "Automation complete!", "progress": 100, "captcha_ready": False}
        return {"status": "success", "message": "Feedback automation completed."}

    except UnexpectedAlertPresentException as e:
        alert_text = "Unknown Alert"
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            alert.accept()
        except Exception:
            pass
        logging.error(f"Caught an unexpected alert: {alert_text} - {e}")
        automation_status = {"message": f"Automation failed: Unexpected Alert - {alert_text}", "progress": -1, "captcha_ready": False}
        return {"status": "error", "message": f"Automation failed: Unexpected Alert - {alert_text}"}

    except Exception as e:
        logging.exception("An unhandled error occurred during automation:") # Use exception for full traceback
        automation_status = {"message": f"Automation failed: {str(e)}", "progress": -1, "captcha_ready": False}
        return {"status": "error", "message": str(e)}
    finally:
        if driver:
            driver.quit()
            current_driver_instance = None # Clear global reference
            logging.info("Selenium WebDriver quit.")
        # Ensure captcha.png is cleaned up even if automation fails at the end
        if os.path.exists(captcha_image_path):
            try:
                os.remove(captcha_image_path)
                logging.info("Cleaned up captcha.png in finally block.")
            except Exception as e:
                logging.warning(f"Could not clean up captcha.png in finally block: {e}")
        
        # Ensure events are cleared in finally block in case of unexpected termination
        captcha_ready_event.clear()
        captcha_submitted_event.clear()
        logging.info("Automation events cleared.")


# Renamed from start_automation to initiate_automation to reflect first step
@app.route('/initiate-automation', methods=['POST'])
def initiate_automation():
    global current_driver_instance, automation_status

    # Reset automation status and events for a fresh start
    automation_status = {"message": "Idle", "progress": 0, "captcha_ready": False}
    captcha_ready_event.clear()
    captcha_submitted_event.clear()
    # Clear the queue in case of previous run's lingering data (unlikely but safe)
    while not captcha_solution_queue.empty():
        try:
            captcha_solution_queue.get_nowait()
            captcha_solution_queue.task_done()
        except queue.Empty:
            pass

    if current_driver_instance:
        logging.warning("Initiate-automation called, but a driver instance is already active. Attempting to quit it.")
        try:
            current_driver_instance.quit()
        except Exception as e:
            logging.error(f"Error quitting existing driver instance: {e}")
        current_driver_instance = None # Ensure it's marked as None

    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"status": "error", "message": "Username and password are required."}), 400

    # Start the automation thread, it will pause for CAPTCHA
    threading.Thread(target=run_feedback_automation_task, args=(username, password)).start()
    
    return jsonify({"status": "initiated", "message": "Automation started. Waiting for CAPTCHA input."})

# New endpoint to receive CAPTCHA solution and resume automation
@app.route('/submit-captcha', methods=['POST'])
def submit_captcha():
    data = request.get_json()
    captcha_solution = data.get('captcha')

    if not captcha_solution:
        return jsonify({"status": "error", "message": "CAPTCHA solution is required."}), 400
    
    # Check if we are truly in a CAPTCHA waiting state before accepting
    if not captcha_ready_event.is_set():
        logging.warning("Submit CAPTCHA called, but automation is not waiting for CAPTCHA.")
        return jsonify({"status": "error", "message": "Automation is not currently waiting for CAPTCHA input."}), 400

    try:
        # Put the solution into the queue for the waiting thread
        captcha_solution_queue.put(captcha_solution)
        # Signal the waiting thread to resume
        captcha_submitted_event.set()
        logging.info("CAPTCHA solution received and signaled to automation thread.")
        return jsonify({"status": "captcha_submitted", "message": "CAPTCHA submitted. Automation resuming..."})
    except Exception as e:
        logging.error(f"Error submitting CAPTCHA: {e}")
        return jsonify({"status": "error", "message": f"Error submitting CAPTCHA: {str(e)}"}), 500

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify(automation_status)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/captcha')
def serve_captcha():
    captcha_path = os.path.join(app.root_path, "static", "captcha.png")
    if os.path.exists(captcha_path):
        response = make_response(send_file(captcha_path, mimetype='image/png'))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    else:
        # Return a transparent 1x1 GIF if no captcha is available
        # This prevents broken image icons while waiting for first capture
        transparent_gif = "R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=="
        response = make_response(base64.b64decode(transparent_gif), 200)
        response.headers['Content-Type'] = 'image/gif'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

if __name__ == '__main__':
    if not os.path.exists('static'):
        os.makedirs('static')
    # Attempt to clean up any leftover captcha.png on server start
    initial_captcha_path = os.path.join(app.root_path, "static", "captcha.png")
    if os.path.exists(initial_captcha_path):
        try:
            os.remove(initial_captcha_path)
            logging.info("Cleaned up initial captcha.png on server startup.")
        except Exception as e:
            logging.warning(f"Could not clean up initial captcha.png on startup: {e}")

    app.run() # For Render deployment