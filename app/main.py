from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, engine
from app.routers import auth, users, actions, jobs
from app.services.job_queue import job_queue


def create_app() -> FastAPI:
    Base.metadata.create_all(bind=engine)
    app = FastAPI(title="Building Control API")

    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(actions.router)
    app.include_router(jobs.router)

    @app.on_event("startup")
    def start_worker():
        job_queue.start()

    return app


app = create_app()
