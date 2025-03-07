import logging
from abc import ABC, abstractmethod
from typing import Annotated
from uuid import UUID

from dishka import FromComponent
from fastapi import HTTPException
from starlette import status

from application.common.interfaces.jwt_service import JWTService
from application.common.interfaces.user_repo import UserRepository
from application.common.interfaces.white_list import TokenWhiteListService
from application.common.auth_server_token_types import (
    AccessToken,
    RefreshToken,
    Fingerprint,
)
from domain.entities.client.value_objects import ClientID
from domain.entities.user.model import User
from domain.entities.user.value_objects import UserID


class IdentityProvider(ABC):
    @abstractmethod
    async def get_current_user_id(self) -> UserID: ...

    @abstractmethod
    async def get_current_user(self) -> User: ...

    @abstractmethod
    def get_current_client_id(self) -> ClientID: ...


logger = logging.getLogger(__name__)


class HttpIdentityProvider(IdentityProvider):
    def __init__(
        self,
        jwt_service: JWTService,
        access_token: AccessToken,
        user_repo: UserRepository,
        refresh_token: RefreshToken,
        token_whitelist_service: Annotated[
            TokenWhiteListService, FromComponent("auth_server")
        ],
        fingerprint: Fingerprint,
    ):
        self.access_token = access_token
        self.jwt_service = jwt_service
        self.user_repo = user_repo
        self.refresh_token = refresh_token
        self.token_whitelist_service = token_whitelist_service
        self.fingerprint = fingerprint

    def _get_refresh_token_payload_(self) -> dict:
        payload = self.jwt_service.decode(self.refresh_token)
        return payload

    def _get_access_token_payload_(self) -> dict:
        payload = self.jwt_service.decode(self.access_token)
        return payload

    async def get_current_user_id(self) -> UserID:
        jti = self._get_refresh_token_jti()
        token_data = await self.token_whitelist_service.get_refresh_token_data(
            jti
        )
        logger.info("token data: %s", token_data)
        if not token_data or token_data.fingerprint != self.fingerprint:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token or fingerprint",
            )
        return UserID(token_data.user_id)

    def _get_refresh_token_jti(self) -> UUID:
        payload = self._get_refresh_token_payload_()
        return payload["jti"]

    async def get_current_user(self) -> User:
        user_id = await self.get_current_user_id()
        user: User = await self.user_repo.get_by_id(user_id)
        return user

    def get_current_client_id(self) -> ClientID:
        payload = self._get_access_token_payload_()
        return payload["client_id"]
