import logging
from dataclasses import dataclass
from typing import cast, TypedDict
from uuid import UUID

from fastapi import HTTPException

from application.auth_as.common.scopes_service import ScopesService
from application.common.client_token_types import ClientAccessToken, ClientRefreshToken
from application.common.interfaces.imedia_storage import StorageServiceInterface
from application.common.interfaces.role_repo import RoleRepository
from application.common.interfaces.user_repo import UserRepository
from application.common.services.auth_code import AuthorizationCodeStorage, AuthCodeData
from application.common.auth_server_token_types import (
    AccessToken,
    RefreshToken,
    Fingerprint,
)
from application.common.interfaces.http_auth import HttpClientService
from application.common.uow import Uow
from domain.entities.user.value_objects import UserID


@dataclass
class CodeToTokenCommand:
    auth_code: str
    code_challenger: str


class CodeToTokenResponse(TypedDict, total=False):
    access_token: ClientAccessToken
    refresh_token: ClientRefreshToken
    email: str
    avatar_path: str


logger = logging.getLogger(__name__)


class CodeToTokenHandler:
    def __init__(
        self,
        auth_service: HttpClientService,
        scopes_service: ScopesService,
        role_repo: RoleRepository,
        auth_code_storage: AuthorizationCodeStorage,
        user_repository: UserRepository,
        uow: Uow,
        s3_storage: StorageServiceInterface,
    ) -> None:
        self.auth_service = auth_service
        self.scopes_service = scopes_service
        self.role_repo = role_repo
        self.auth_code_storage = auth_code_storage
        self.user_repository = user_repository
        self.uow = uow
        self.s3_storage = s3_storage

    def _validate_pkce(
        self, user_code_challenger: str, real_code_challenger: str
    ) -> bool:
        return user_code_challenger == real_code_challenger

    async def handle(
        self, command: CodeToTokenCommand, fingerprint: Fingerprint
    ) -> CodeToTokenResponse:
        auth_code_data: AuthCodeData = await self.auth_code_storage.retrieve_auth_code_data(
            command.auth_code
        )
        if not auth_code_data:
            raise HTTPException(
                status_code=400, detail="Invalid authorization code"
            )

        real_code_challenger = auth_code_data["code_challenger"]
        if not self._validate_pkce(
            command.code_challenger, real_code_challenger
        ):
            raise HTTPException(status_code=400, detail="Invalid PKCE")

        user = await self.user_repository.get_by_id(
            UserID(UUID(auth_code_data["user_id"]))
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        client_id = int(auth_code_data["client_id"])
        rs_ids = auth_code_data["rs_ids"]
        await self.user_repository.add_rs_to_user(user.id, rs_ids)
        result = {
            k: getattr(getattr(user, k), "value", getattr(user, k))
            for k in auth_code_data["user_data_needed"] if k != "avatar_path"
        }
        try:
            if idx := auth_code_data["user_data_needed"].index("avatar_path"):
                result["avatar_path"] = self.s3_storage.get_presigned_avatar_url(user.id.value.hex)
                auth_code_data["user_data_needed"].pop(idx)
        except ValueError: ...

        user_roles = await self.role_repo.get_user_roles_by_rs_id(
            user_id=user.id, rs_ids=rs_ids
        )
        logger.info(f"User roles: %s, rs_ids: %s", user_roles, rs_ids)
        user_scopes = (
            self.scopes_service.calculate_full_user_scopes_for_client(
                user_roles
            )
        )
        tokens = await self.auth_service.create_and_save_tokens(
            user, user_scopes, client_id, fingerprint,
        )
        await self.auth_code_storage.delete_auth_code_data(command.auth_code)
        result.update(**tokens)
        await self.uow.commit()
        return result
