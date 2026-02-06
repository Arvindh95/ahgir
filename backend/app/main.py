from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, events, guest, health
from app.error_handler import register_error_handlers
from app.config import settings

app = FastAPI(title="PicUr API", version="1.0.0")

# Register error handlers
register_error_handlers(app)

# CORS configuration
origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(guest.router)
app.include_router(health.router)
