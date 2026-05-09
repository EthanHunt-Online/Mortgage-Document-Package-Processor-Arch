"""FastAPI entrypoint for the mortgage document package processor."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI

from mortgage_processor.models import PackageRequest
from mortgage_processor.pipeline import process_package

app = FastAPI(
    title="Mortgage Document Package Processor",
    summary="Cost-aware mortgage PDF package classification, grouping, validation, and exception reporting.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Return service health for load balancers and orchestration."""

    return {"status": "ok"}


@app.post("/process-package")
def process_package_endpoint(request: PackageRequest) -> dict:
    """Process normalized package pages into documents and exceptions."""

    return asdict(process_package(request))
