#!/bin/bash
# Script to start or stop local backend and frontend for testing
# Usage: ./dev.sh start|stop

FRONTEND_DIR="/home/craig/projects/school/frontend"
BACKEND_DIR="/home/craig/projects/school/backend"
FRONTEND_PID_FILE="/tmp/school_frontend.pid"
BACKEND_PID_FILE="/tmp/school_backend.pid"

start() {
  echo "Starting frontend..."
  cd "$FRONTEND_DIR"
  nohup npm run dev > "$FRONTEND_DIR/frontend.log" 2>&1 &
  FRONTEND_PID=$!
  echo $FRONTEND_PID > "$FRONTEND_PID_FILE"
  echo "Frontend started with PID $FRONTEND_PID (log: $FRONTEND_DIR/frontend.log)"

  echo "Starting backend..."
  cd "$BACKEND_DIR"
  nohup uvicorn main:app --reload > "$BACKEND_DIR/backend.log" 2>&1 &
  BACKEND_PID=$!
  echo $BACKEND_PID > "$BACKEND_PID_FILE"
  echo "Backend started with PID $BACKEND_PID (log: $BACKEND_DIR/backend.log)"
}

stop() {
  if [ -f "$FRONTEND_PID_FILE" ]; then
    FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
    echo "Stopping frontend (PID $FRONTEND_PID)..."
    kill $FRONTEND_PID && rm "$FRONTEND_PID_FILE"
  else
    echo "Frontend PID file not found."
  fi

  if [ -f "$BACKEND_PID_FILE" ]; then
    BACKEND_PID=$(cat "$BACKEND_PID_FILE")
    echo "Stopping backend (PID $BACKEND_PID)..."
    kill $BACKEND_PID && rm "$BACKEND_PID_FILE"
  else
    echo "Backend PID file not found."
  fi
}

case "$1" in
  start)
    start
    ;;
  stop)
    stop
    ;;
  *)
    echo "Usage: $0 start|stop"
    exit 1
    ;;
esac
