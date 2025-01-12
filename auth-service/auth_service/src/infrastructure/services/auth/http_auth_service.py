import logging
from uuid import UUID

from fastapi import HTTPException

from application.common.exceptions import FingerprintMismatchException
from application.common.interfaces.http_auth import HttpAuthService
from application.common.interfaces.jwt_service import JWTService
from application.common.interfaces.white_list import TokenWhiteListService
from application.common.services.pkce import (
    PKCEService,
)
from application.common.token_types import (
    Fingerprint,
    AccessToken,
    RefreshToken,
    Payload,
)
from application.common.interfaces.token_creation import TokenCreationService
from application.common.interfaces.user_repo import UserRepository
from domain.entities.user.model import User
from domain.entities.user.value_objects import Email, RawPassword, UserID
from domain.common.services.pwd_service import PasswordHasher
from infrastructure.services.auth.config import JWTSettings
from application.common.services.auth_code import (
    AuthorizationCodeStorage,
)

logger = logging.getLogger(__name__)


class HttpAuthServiceImpl(HttpAuthService):
    """Сервис для аутентификации, обновления и управления токенами."""

    def __init__(
        self,
        user_repository: UserRepository,
        jwt_service: JWTService,
        token_creation_service: TokenCreationService,
        token_whitelist_service: TokenWhiteListService,
        hash_service: PasswordHasher,
        jwt_settings: JWTSettings,
        auth_code_storage: AuthorizationCodeStorage,
        pkce_service: PKCEService,
    ):
        self.user_repository = user_repository
        self.jwt_service = jwt_service
        self.token_creation_service = token_creation_service
        self.token_whitelist_service = token_whitelist_service
        self.hash_service = hash_service
        self.jwt_settings = jwt_settings
        self.auth_code_storage = auth_code_storage
        self.pkce_service = pkce_service

    async def _token_to_user(
        self, refresh_token: RefreshToken, fingerprint: Fingerprint
    ) -> User:
        jti = self._get_token_jti(refresh_token)
        token_data = await self.token_whitelist_service.get_refresh_token_data(
            jti
        )
        logger.info("tokend data: %s, jti: %s", token_data, jti)
        if not token_data or token_data.fingerprint != fingerprint:
            raise HTTPException(
                status_code=401, detail="Invalid refresh token or fingerprint"
            )
        user: User = await self.user_service.get_by_id(token_data.user_id)  # type: ignore
        return user

    async def authenticate_user(
        self, email: Email, password: RawPassword, fingerprint: Fingerprint
    ) -> tuple[AccessToken, RefreshToken]:
        user = await self.user_repository.get_by_email(email)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        self.hash_service.check_password(password, user.hashed_password)
        return await self.create_and_save_tokens(user, fingerprint)

    async def refresh_tokens(
        self, refresh_token: RefreshToken, fingerprint: Fingerprint
    ) -> tuple[AccessToken, RefreshToken]:
        user = await self._token_to_user(refresh_token, fingerprint)
        return await self.create_and_save_tokens(user, fingerprint)

    def _get_token_jti(self, refresh_token: RefreshToken) -> UUID:
        payload = self.jwt_service.decode(refresh_token)
        return payload["jti"]

    async def revoke(self, refresh_token: RefreshToken) -> None:
        jti = self._get_token_jti(refresh_token)
        await self.token_whitelist_service.remove_token(jti)

    async def invalidate_other_tokens(
        self, refresh_token: RefreshToken, fingerprint: Fingerprint
    ) -> None:
        payload: Payload = self.jwt_service.decode(refresh_token)
        jti = payload["jti"]
        if not await self.token_whitelist_service.is_fingerprint_matching(
            jti, fingerprint
        ):
            raise FingerprintMismatchException()
        user_id: UUID = payload["sub"]  # type: ignore
        await self.token_whitelist_service.remove_tokens_except_current(
            jti, user_id
        )

    async def refresh_access_token(
        self, refresh_token: RefreshToken, fingerprint: Fingerprint
    ) -> AccessToken:
        user = await self._token_to_user(refresh_token, fingerprint)
        return self.token_creation_service.create_access_token(user)

    async def authenticate_by_auth_code(
        self,
        auth_code: str,
        redirect_url: str,
        fingerprint: Fingerprint,
        code_challenger: str,
    ) -> tuple[AccessToken, RefreshToken]:
        auth_code_data = await self.auth_code_storage.retrieve_auth_code_data(
            auth_code
        )
        if not auth_code_data:
            raise HTTPException(
                status_code=400, detail="Invalid authorization code"
            )

        if auth_code_data["redirect_url"] != redirect_url:
            raise HTTPException(status_code=400, detail="Invalid redirect URL")

        real_code_challenger = auth_code_data["code_challenger"]
        if not self._validate_pkce(code_challenger, real_code_challenger):
            raise HTTPException(status_code=400, detail="Invalid PKCE")

        user = await self.user_repository.get_by_id(
            UserID(UUID(auth_code_data["user_id"]))
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        tokens = await self.create_and_save_tokens(user, fingerprint)
        await self.auth_code_storage.delete_auth_code_data(auth_code)
        return tokens

    async def create_and_save_tokens(
        self, user: User, fingerprint: Fingerprint
    ) -> tuple[AccessToken, RefreshToken]:
        """Создаёт и сохраняет токены."""
        access_token = self.token_creation_service.create_access_token(user)
        refresh_token_data = (
            await self.token_creation_service.create_refresh_token(
                user, fingerprint
            )
        )
        await self.token_whitelist_service.save_refresh_token(
            refresh_token_data,
            self.jwt_settings.refresh_token_by_user_limit,
        )
        return access_token, refresh_token_data.token

    def _validate_pkce(
        self, user_code_challenger: str, real_code_challenger: str
    ) -> bool:
        return user_code_challenger == real_code_challenger
