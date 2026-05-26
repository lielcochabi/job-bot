FROM python:3.11-slim

# System dependencies for Playwright Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libcairo2 \
    libx11-6 libxext6 libxrender1 libxss1 \
    wget ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser
RUN playwright install chromium

# Copy source code
COPY . .

# Streamlit config — disable telemetry, allow CORS for Cloud Run
RUN mkdir -p /root/.streamlit && cat > /root/.streamlit/config.toml << 'EOF'
[server]
headless = true
enableCORS = false
enableXsrfProtection = false

[browser]
gatherUsageStats = false
EOF

# Cloud Run injects $PORT (default 8080)
EXPOSE 8080

CMD streamlit run app.py \
    --server.port=${PORT:-8080} \
    --server.address=0.0.0.0
