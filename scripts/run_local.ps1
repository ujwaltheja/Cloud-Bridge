# Cloud Bridge - Simple Local Prototype Runner (Windows PowerShell)
# No Docker required

Write-Host "Starting Cloud Bridge (Prototype Mode - No Docker)" -ForegroundColor Cyan

# Backend
# Note: uvicorn --reload uses multiprocessing spawn which crashes on Python 3.14 (logging bug).
# watchfiles provides the same auto-reload without spawning a subprocess.
Write-Host "`n[1/2] Starting Backend..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd backend; `$py = (python -c 'import sys; print(sys.executable)'); python -m watchfiles `"`$py -m uvicorn app.main:app --host 0.0.0.0 --port 8000`" app"

# Frontend
Write-Host "`n[2/2] Starting Frontend..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd frontend; npm run dev"

Write-Host "`nBoth services are starting in separate windows." -ForegroundColor Yellow
Write-Host "Backend:  http://localhost:8000/api/v1/docs" -ForegroundColor White
Write-Host "Frontend: http://localhost:3000" -ForegroundColor White
Write-Host "`nTip: Run 'alembic upgrade head' inside the backend folder on first run." -ForegroundColor Gray
