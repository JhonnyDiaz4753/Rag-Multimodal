"""Punto de entrada para Uvicorn (``src.api.main:app``)."""

from src.api.app import create_app


app = create_app()
