import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from src.api.routes import router

app = FastAPI(title='WM 2026 Predictor API')
app.include_router(router)
@app.on_event('startup')
def startup_event():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(perform_elo_sync, 'cron', hour=4, minute=0)
    scheduler.start()
    print('Scheduler started. Elo sync scheduled for 04:00 AM daily.')

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
