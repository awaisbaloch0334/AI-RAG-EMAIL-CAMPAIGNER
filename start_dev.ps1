Write-Host "===================================================" -ForegroundColor Cyan
Write-Host " Embeddable RAG Chatbot Platform - Development Mode" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/3] Ensuring PostgreSQL and Redis Docker containers are running..." -ForegroundColor Yellow
docker compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Docker compose failed to start. Ensure Docker Desktop is running." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "`n[2/3] Starting Celery Background Worker in a new terminal..." -ForegroundColor Yellow
Start-Process cmd -ArgumentList '/k', 'cd /d', "`"$PSScriptRoot\backend`"", '&&', '.\.venv\Scripts\python.exe', '-m', 'celery', '-A', 'app.tasks.celery_app.celery_app', 'worker', '--loglevel=info', '-P', 'solo'

Write-Host "`n[3/3] Starting FastAPI Uvicorn Server in a new terminal..." -ForegroundColor Yellow
Start-Process cmd -ArgumentList '/k', 'cd /d', "`"$PSScriptRoot\backend`"", '&&', '.\.venv\Scripts\python.exe', '-m', 'uvicorn', 'app.main:app', '--port', '8000', '--reload'

Write-Host ""
Write-Host "===================================================" -ForegroundColor Green
Write-Host " Both services launched successfully!" -ForegroundColor Green
Write-Host "  * Customer Admin Dashboard: http://localhost:8000/dashboard" -ForegroundColor White
Write-Host "  * Chat Widget Demo:         http://localhost:8000/static/demo.html" -ForegroundColor White
Write-Host "  * API Documentation:        http://localhost:8000/docs" -ForegroundColor White
Write-Host "===================================================" -ForegroundColor Green

