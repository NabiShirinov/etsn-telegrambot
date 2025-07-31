FROM python:3.9

# Create non-root user
RUN useradd -m -u 1000 user
USER user

# Ensure pip user binaries are in PATH
ENV PATH="/home/user/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY --chown=user requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY --chown=user . /app

# Run app
CMD ["python", "app.py"]
