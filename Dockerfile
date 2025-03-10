FROM python:3.9-slim

# Install dependencies for Node.js, Spectral CLI, and the requests module
RUN apt-get update && apt-get install -y curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_16.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @stoplight/spectral-cli \
    && pip install requests \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy the application files into the container
COPY main.py /app/main.py
COPY api_spec.yaml /app/api_spec.yaml
COPY ruleset.yaml /app/ruleset.yaml

# Run the application
CMD ["python", "main.py", "api_spec.yaml", "ruleset.yaml"]
