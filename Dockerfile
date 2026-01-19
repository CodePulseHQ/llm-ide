# Multi-Language Refactor MCP Server Dockerfile
FROM python:3.14-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    git \
    curl \
    libxml2-dev \
    libxslt-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy pyproject.toml and install dependencies first (for better caching)
COPY pyproject.toml ./
RUN pip install --upgrade pip setuptools wheel

# Install the package in development mode
# This installs all dependencies including tree-sitter, lxml, etc.
COPY . .
RUN pip install -e .

# Create non-root user for security
RUN groupadd -r mcpuser && useradd -r -g mcpuser mcpuser
RUN chown -R mcpuser:mcpuser /app
USER mcpuser

# Expose port (optional, for future HTTP interface)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from refactor_mcp.languages import list_supported_languages; print('OK' if len(list_supported_languages()) >= 6 else 'FAIL')"

# Default command - run the MCP server
CMD ["python", "-m", "refactor_mcp.server"]