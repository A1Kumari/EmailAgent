#!/bin/bash
# ═══════════════════════════════════════════════════════
# Docker Entrypoint — Email Agent
#
# R5 (AC6): Validates required environment variables
# R5 (AC8): Handles signals for graceful shutdown
# R9 (AC7): Includes container ID in startup logs
# ═══════════════════════════════════════════════════════

set -e

# ──────────────────────────────────────────────
# Color codes for output
# ──────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "══════════════════════════════════════════"
echo "  Email Agent — Docker Container Starting"
echo "══════════════════════════════════════════"
echo ""

# ──────────────────────────────────────────────
# R5 (AC6): Validate required environment variables
# Exit with non-zero status if any are missing
# ──────────────────────────────────────────────
MISSING_VARS=()

if [ -z "$GMAIL_EMAIL" ]; then
    MISSING_VARS+=("GMAIL_EMAIL")
fi

if [ -z "$GMAIL_APP_PASSWORD" ]; then
    MISSING_VARS+=("GMAIL_APP_PASSWORD")
fi

if [ -z "$GEMINI_API_KEY" ]; then
    MISSING_VARS+=("GEMINI_API_KEY")
fi

if [ ${#MISSING_VARS[@]} -ne 0 ]; then
    echo -e "${RED}══════════════════════════════════════════${NC}"
    echo -e "${RED}  ERROR: Missing required environment variables${NC}"
    echo -e "${RED}══════════════════════════════════════════${NC}"
    echo ""
    for var in "${MISSING_VARS[@]}"; do
        echo -e "  ${RED}❌ $var is not set${NC}"
    done
    echo ""
    echo "  Set these in your .env file or docker-compose.yml:"
    echo ""
    echo "    GMAIL_EMAIL=your-email@gmail.com"
    echo "    GMAIL_APP_PASSWORD=your-app-password"
    echo "    GEMINI_API_KEY=your-gemini-api-key"
    echo ""
    echo "  Or pass them with docker run:"
    echo "    docker run -e GMAIL_EMAIL=... -e GMAIL_APP_PASSWORD=... -e GEMINI_API_KEY=... email-agent"
    echo ""
    exit 1
fi

# ──────────────────────────────────────────────
# Validate config file exists
# ──────────────────────────────────────────────
if [ ! -f "/app/config/config.yaml" ]; then
    echo -e "${YELLOW}⚠️  No config.yaml found in /app/config/${NC}"
    echo "  Make sure to mount your config directory:"
    echo "    docker run -v ./config:/app/config email-agent"
    echo ""

    # Check if example config exists to copy
    if [ -f "/app/config/config.example.yaml" ]; then
        echo -e "${YELLOW}  Found config.example.yaml — copying as config.yaml${NC}"
        cp /app/config/config.example.yaml /app/config/config.yaml
    else
        echo -e "${RED}  No config file available. Exiting.${NC}"
        exit 1
    fi
fi

# ──────────────────────────────────────────────
# Ensure log directory is writable
# ──────────────────────────────────────────────
if [ ! -w "/app/logs" ]; then
    echo -e "${YELLOW}⚠️  /app/logs is not writable. Logs may not persist.${NC}"
fi

# ──────────────────────────────────────────────
# R9 (AC7): Log startup info with container ID
# ──────────────────────────────────────────────
CONTAINER_ID=${CONTAINER_ID:-$(hostname)}
echo -e "${GREEN}✅ Environment validated successfully${NC}"
echo ""
echo "  Container ID:    $CONTAINER_ID"
echo "  Gmail Account:   $GMAIL_EMAIL"
echo "  Dry Run:         ${DRY_RUN:-true}"
echo "  Log Level:       ${LOG_LEVEL:-INFO}"
echo ""

# R7: Log feature flags if set
echo "  Feature Flags:"
echo "    JSON Mode:        ${FEATURE_JSON_MODE:-true}"
echo "    Function Calling: ${FEATURE_FUNCTION_CALLING:-true}"
echo "    Cost Tracking:    ${FEATURE_COST_TRACKING:-true}"
echo "    Thread Depth:     ${FEATURE_THREAD_DEPTH:-5}"
echo ""
echo "══════════════════════════════════════════"
echo ""

# ──────────────────────────────────────────────
# R5 (AC8): Signal handling for graceful shutdown
# ──────────────────────────────────────────────
# Trap SIGTERM and SIGINT for graceful shutdown
# Forward signals to the Python process
shutdown() {
    echo ""
    echo "══════════════════════════════════════════"
    echo "  Received shutdown signal — stopping gracefully..."
    echo "══════════════════════════════════════════"

    # Send SIGTERM to the Python process
    if [ -n "$PID" ]; then
        kill -TERM "$PID" 2>/dev/null
        # Wait for process to finish (up to 25 seconds)
        wait "$PID" 2>/dev/null
    fi

    echo "  Email agent stopped cleanly."
    exit 0
}

trap shutdown SIGTERM SIGINT

# ──────────────────────────────────────────────
# Start the application
# ──────────────────────────────────────────────
echo "Starting email agent..."

# Run the command passed to the container (default: python main.py)
# Use exec to replace shell with Python process for signal forwarding
# But we need & + wait pattern for trap to work
"$@" &
PID=$!

# Wait for the process to complete
wait "$PID"
EXIT_CODE=$?

echo "Email agent exited with code: $EXIT_CODE"
exit $EXIT_CODE