#!/bin/bash
# ─────────────────────────────────────────────────────────
#  start.sh — Boot both the Python backend and React frontend
# ─────────────────────────────────────────────────────────
#  Usage:
#    ./start.sh                  # default threshold 1.0%
#    ./start.sh --threshold 0.3  # custom threshold
#
#  Press Ctrl+C to stop both services.
# ─────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  ⚡ Arbitrage Dashboard — Starting Services${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# ── 1. Start Python WebSocket backend ────────────────────
echo -e "${GREEN}[1/2]${NC} Starting Python WebSocket backend..."
source venv/bin/activate
python ws_server.py "$@" &
PYTHON_PID=$!
echo -e "      PID: ${YELLOW}${PYTHON_PID}${NC}"

# Give the backend a moment to start
sleep 2

# ── 2. Start Vite dev server ─────────────────────────────
echo -e "${GREEN}[2/2]${NC} Starting React frontend (Vite)..."
cd frontend && npm run dev &
VITE_PID=$!
echo -e "      PID: ${YELLOW}${VITE_PID}${NC}"

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${GREEN}🚀 Services running:${NC}"
echo -e "     Dashboard:  ${CYAN}http://localhost:5173${NC}"
echo -e "     WebSocket:  ${CYAN}ws://127.0.0.1:8765${NC}"
echo -e "     Backend:    PID ${YELLOW}${PYTHON_PID}${NC}"
echo -e "     Frontend:   PID ${YELLOW}${VITE_PID}${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop both services."
echo ""

# ── Trap Ctrl+C to clean up both processes ────────────────
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down services...${NC}"
    kill "$PYTHON_PID" 2>/dev/null
    kill "$VITE_PID" 2>/dev/null
    wait "$PYTHON_PID" 2>/dev/null
    wait "$VITE_PID" 2>/dev/null
    echo -e "${GREEN}All services stopped.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for either process to exit
wait
