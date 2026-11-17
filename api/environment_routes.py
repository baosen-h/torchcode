from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


class EnvironmentSelection(BaseModel):
    environment_id: str = Field(min_length=1, max_length=100)


class EnvironmentCreation(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    python_version: str = "3.11"


class PythonInstallation(EnvironmentSelection):
    python_version: str = "3.11"


class PackageInstallation(EnvironmentSelection):
    packages: list[str] = Field(min_length=1, max_length=30)


def create_environment_router(manager):
    router = APIRouter(prefix="/api/environments", tags=["environments"])

    def require_local_request(request):
        host = request.url.hostname
        if host not in {"localhost", "127.0.0.1", "::1", "testserver"}:
            raise HTTPException(status_code=403, detail="环境管理仅支持本机访问")
        origin = request.headers.get("origin")
        if origin:
            from urllib.parse import urlsplit
            if urlsplit(origin).hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise HTTPException(status_code=403, detail="请从本机 TorchCode 页面管理环境")
        if request.client and request.client.host not in {"localhost", "127.0.0.1", "::1", "testclient"}:
            raise HTTPException(status_code=403, detail="环境管理仅支持本机访问")

    @router.get("")
    def list_environments(request: Request, refresh: bool = False):
        require_local_request(request)
        return manager.snapshot(refresh)

    @router.get("/current")
    def current_environment():
        return manager.current()

    @router.put("/current")
    def select_environment(body: EnvironmentSelection, request: Request):
        require_local_request(request)
        return {"selected": manager.select(body.environment_id), "error": ""}

    @router.post("", status_code=202)
    def create_environment(body: EnvironmentCreation, request: Request):
        require_local_request(request)
        return {"job_id": manager.create(body.name, body.python_version)}

    @router.post("/python", status_code=202)
    def install_python(body: PythonInstallation, request: Request):
        require_local_request(request)
        return {"job_id": manager.install_python(body.environment_id, body.python_version)}

    @router.post("/packages", status_code=202)
    def install_packages(body: PackageInstallation, request: Request):
        require_local_request(request)
        return {"job_id": manager.install_packages(body.environment_id, body.packages)}

    return router
