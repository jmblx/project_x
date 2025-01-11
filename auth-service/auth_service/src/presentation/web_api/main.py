import logging
import os
from contextlib import asynccontextmanager
from dataclasses import asdict

from dishka.integrations.fastapi import (
    setup_dishka,
)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

# import core.db.logs  # noqa: F401
from core.di.container import container
from infrastructure.log.main import configure_logging
from presentation.web_api.config import load_config
from presentation.web_api.routes.auth.router import auth_router
from presentation.web_api.routes.client.client_router import client_router
from presentation.web_api.exceptions import setup_exception_handlers
from presentation.web_api.routes.investments.router import inv_router
from presentation.web_api.routes.registration.router import reg_router
from presentation.web_api.routes.role.router import role_router
from presentation.web_api.routes.strategy.router import strategy_router
from presentation.web_api.routes.token_manage.router import token_manage_router
from presentation.web_api.middlewares import setup_middlewares
from presentation.web_api.routes.healthcheck.router import healthcheck_router
from presentation.web_api.routes.email_confirmation.router import (
    email_conf_router,
)
from presentation.web_api.routes.user_account.router import user_account_router
from presentation.web_api.routes.user_password.router import (
    user_password_router,
)


@asynccontextmanager  # type: ignore
async def lifespan(app: FastAPI) -> None:  # type: ignore
    yield
    await app.state.dishka_container.close()  # type: ignore

logger = logging.getLogger(__name__)

# logstash_handler = TCPLogstashHandler("logstash", 50000)
# logger.addHandler(logstash_handler)



config = load_config()
def create_app() -> FastAPI:
    app = FastAPI(
        lifespan=lifespan, root_path="/api", default_response_class=ORJSONResponse
    )
    app.include_router(reg_router)
    app.include_router(client_router)
    app.include_router(auth_router)
    app.include_router(role_router)
    app.include_router(token_manage_router)
    app.include_router(inv_router)
    app.include_router(strategy_router)
    app.include_router(healthcheck_router)
    app.include_router(email_conf_router)
    app.include_router(user_password_router)
    app.include_router(user_account_router)
    setup_exception_handlers(app)
    # setup_middlewares(app)
    return app


def create_production_app():
    app = create_app()
    setup_dishka(container=container, app=app)
    return app

if os.getenv("GUNICORN_MAIN", "false").lower() not in ("false", "0"):

    def main():
        from presentation.web_api.gunicorn.application import Application

        configure_logging(config.app_logging_config)

        gunicorn_app = Application(
            application=create_production_app(),
            options={
                **asdict(config.gunicorn_config),  # Опции Gunicorn
                "logconfig_dict": config.app_logging_config,  # Конфиг логирования
            },
        )
        logger.info(
            "Launch app", extra={"config": {"ya": "kros", "level": "DEBUG"}}
        )
        gunicorn_app.run()

    if __name__ == "__main__":
        main()

else:
    configure_logging(config.app_logging_config)
    logger.info(
        "Launch app", extra={"config": {"ya": "ebal", "level": "DEBUG"}}
    )
    app = create_production_app()