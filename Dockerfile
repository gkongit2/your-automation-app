FROM python:3.10-slim

# Install Chrome & Chromedriver
RUN apt-get update && apt-get install -y \
    chromium chromium-driver curl unzip && \
    rm -rf /var/lib/apt/lists/*

# Set environment variables for Selenium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app files
COPY . .

# Run your app
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000"]
