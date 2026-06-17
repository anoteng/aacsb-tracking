from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
import os

from config import get_settings
from routers import auth_router, aol_router, users_router, admin_router, research_router
from routers.passkey import router as passkey_router
from routers.dashboard import router as dashboard_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="AACSB Accreditation Management System",
    version="1.0.0",
    root_path=settings.app_base_path,
)

cors_origins = [settings.app_origin]
if settings.debug:
    cors_origins += ["http://localhost", "http://127.0.0.1"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(aol_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(research_router, prefix="/api")
app.include_router(passkey_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")


# Health check
@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


# Mount static files for frontend
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")


def serve_page(path: str) -> HTMLResponse:
    """Serve an HTML page, rewriting hardcoded /aacsb/ paths to the correct base path."""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if settings.app_base_path != "/aacsb":
        for quote in ('"', "'", "`"):
            content = content.replace(f"{quote}/aacsb/", f"{quote}{settings.app_base_path}/")
    return HTMLResponse(content)


# Serve frontend pages
@app.get("/")
async def root():
    return RedirectResponse(url=f"{settings.app_base_path}/dashboard")


@app.get("/dashboard")
async def dashboard_page():
    page_path = os.path.join(frontend_path, "dashboard.html")
    if os.path.exists(page_path):
        return serve_page(page_path)
    return {"message": "Dashboard page not found"}


@app.get("/aol")
@app.get("/aol/")
async def aol_index():
    index_path = os.path.join(frontend_path, "aol", "index.html")
    if os.path.exists(index_path):
        return serve_page(index_path)
    return {"message": "AOL frontend not found"}


@app.get("/aol/programme/{programme_id}")
async def aol_programme(programme_id: int):
    page_path = os.path.join(frontend_path, "aol", "programme.html")
    if os.path.exists(page_path):
        return serve_page(page_path)
    return {"message": "Programme page not found"}


@app.get("/aol/courses")
async def aol_courses():
    page_path = os.path.join(frontend_path, "aol", "courses.html")
    if os.path.exists(page_path):
        return serve_page(page_path)
    return {"message": "Courses page not found"}




@app.get("/aol/course/{course_id}")
async def aol_course(course_id: int):
    page_path = os.path.join(frontend_path, "aol", "course.html")
    if os.path.exists(page_path):
        return serve_page(page_path)
    return {"message": "Course page not found"}


@app.get("/settings")
async def settings_page():
    page_path = os.path.join(frontend_path, "aol", "settings.html")
    if os.path.exists(page_path):
        return serve_page(page_path)
    return {"message": "Settings page not found"}


# Legacy URL — prod nginx redirects the same way
@app.get("/aol/settings")
async def aol_settings():
    return RedirectResponse(url=f"{settings.app_base_path}/settings", status_code=301)


@app.get("/qualifications")
@app.get("/qualifications/")
async def qualifications_page():
    page_path = os.path.join(frontend_path, "qualifications.html")
    if os.path.exists(page_path):
        return serve_page(page_path)
    return {"message": "Qualifications page not found"}


@app.get("/admin")
@app.get("/admin/")
async def admin_page():
    page_path = os.path.join(frontend_path, "admin.html")
    if os.path.exists(page_path):
        return serve_page(page_path)
    return {"message": "Admin page not found"}


@app.get("/login")
async def login_page():
    index_path = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_path):
        return serve_page(index_path)
    return {"message": "Login page not found"}


# Research section
@app.get("/research")
@app.get("/research/")
async def research_index():
    page_path = os.path.join(frontend_path, "research.html")
    if os.path.exists(page_path):
        return serve_page(page_path)
    return {"message": "Research page not found"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
