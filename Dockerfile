# Use Python 3.10 slim image
FROM python:3.10-slim

# Set work directory
WORKDIR /app

# Install system dependencies required by Playwright + ffmpeg + fonts
RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    wget \
    curl \
    fonts-dejavu-core \
    fonts-freefont-ttf \
    fonts-unifont \
    fonts-noto-core \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for caching)
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium only (skip --with-deps to avoid broken fonts)
RUN playwright install chromium

# Copy the rest of the code
COPY . .

# Start your bot
CMD ["python", "mng2.py"]
