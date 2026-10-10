FROM python:3.10-slim

# Install system dependencies: ffmpeg, nodejs (for YouTube cipher decoding), git, curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    npm \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces uses non-root user with UID 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR $HOME/app

# Install Python requirements
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY --chown=user . .

# Ensure upload/output directories exist
RUN mkdir -p uploads outputs thumbs

# Hugging Face Spaces default port
EXPOSE 7860

CMD ["python", "app.py"]
