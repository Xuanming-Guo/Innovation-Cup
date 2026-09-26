# Coordination backend

This package exposes two separate processes over one shared Python package:

- `python -m uvicorn coordination.api.main:app` runs the FastAPI service.
- `python -m coordination.worker.main` runs durable background work. In the foundation slice it reports
  process readiness only; queue consumption is introduced by its dedicated issue.

No hosted database or model provider is contacted merely by importing or starting the package.
The repository runner adds `src/` to `PYTHONPATH`; this is an application, not a published
Python distribution.
