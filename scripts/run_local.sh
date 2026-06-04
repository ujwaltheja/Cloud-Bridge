#!/bin/bash
# Cloud Bridge - Simple Local Prototype Runner (Unix/Mac)
# No Docker required

echo "Starting Cloud Bridge (Prototype Mode - No Docker)"

echo "[1/2] Starting Backend..."
(cd backend && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000) &

echo "[2/2] Starting Frontend..."
(cd frontend && npm run dev) &

echo ""
echo "Backend:  http://localhost:8000/api/v1/docs"
echo "Frontend: http://localhost:5173"
echo ""
echo "First time? Run this in the backend folder:"
echo "   alembic upgrade head"
