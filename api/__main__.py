"""Run the API with validated local defaults: python -m api."""

import uvicorn

from src.settings import Settings
from src.observability import configure_logging

if __name__ == "__main__":
    settings = Settings.from_environment()
    configure_logging(settings.log_level)
    uvicorn.run("api.main:app", host=settings.api_host, port=settings.api_port,
                access_log=False, log_level=settings.log_level.lower(), log_config=None)
