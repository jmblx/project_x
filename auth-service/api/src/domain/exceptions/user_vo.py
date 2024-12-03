from domain.common.exceptions.base import DomainError


class InvalidPasswordError(DomainError): ...


class EmptyValueError(DomainError): ...


class InvalidCharacterError(DomainError): ...


class InvalidFilePathError(DomainError): ...


class InvalidRegisterDateError(DomainError): ...


class InvalidUserIDError(DomainError): ...


class InvalidEmailError(DomainError): ...


