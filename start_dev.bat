@echo off
echo ===================================================
echo  Embeddable RAG Chatbot Platform - Development Mode
echo ===================================================
echo.

echo [1/3] Ensuring PostgreSQL and Redis Docker containers are running...
docker compose up -d
if %errorlevel% neq 0 (
    echo [ERROR] Docker compose failed to start. Ensure Docker Desktop is running.
    pause
    exit /b %errorlevel%
)

echo.
echo [2/3] Starting Celery Background Worker in a new terminal...
start "Celery Background Worker" cmd /k "cd /d %~dp0backend && .\.venv\Scripts\python.exe -m celery -A app.tasks.celery_app.celery_app worker --loglevel=info -P solo"

echo.
echo [3/3] Starting FastAPI Uvicorn Server in a new terminal...
start "FastAPI Server" cmd /k "cd /d %~dp0backend && .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload"

echo.
echo ===================================================
echo  Both services launched successfully!
echo   * Customer Admin Dashboard: http://localhost:8000/dashboard
echo   * Chat Widget Demo:         http://localhost:8000/static/demo.html
echo   * API Documentation:        http://localhost:8000/docs
echo ===================================================
echo.

