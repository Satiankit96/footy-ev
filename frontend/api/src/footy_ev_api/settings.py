"""Pydantic Settings for the footy-ev API."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """UI-specific configuration loaded from frontend/.env."""

    ui_operator_token: str = ""
    ui_api_bind_host: str = "127.0.0.1"
    ui_api_port: int = 8000
    ui_web_port: int = 3000
    warehouse_path: str = "../../data/footy_ev.duckdb"

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8"}
