# backend/app/worker/__init__.py
"""Celery 工作进程模块"""

from app.worker.celery_app import celery_app
from app.worker.tasks import execute_tool_task

__all__ = ["celery_app", "execute_tool_task"]
