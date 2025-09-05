# Use Python 3.10 to avoid greenlet / compatibility issues
FROM python:3.10-slim

# Set work directory
WORKDIR /app

# Install system dependencies (added git)
RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    wget \
    curl \
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
    fonts-dejavu-core \
    fonts-freefont-ttf \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for caching)
COPY requirements.txt .

# Upgrade pip (avoids old pip bugs) and install Python dependencies
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium with dependencies
RUN playwright install --with-deps chromium

# Copy the rest of the code
COPY . .

# Start your bot
CMD ["python", "mng2.py"]
