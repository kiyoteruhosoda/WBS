from __future__ import annotations


class DomainException(Exception):
    pass

class NotFoundError(DomainException):
    def __init__(self, resource: str, id: int | str) -> None:
        self.resource = resource
        self.id = id
        super().__init__(f"{resource} with id={id} not found")

class ValidationError(DomainException):
    pass

class ConflictError(DomainException):
    pass

class CyclicDependencyError(ConflictError):
    def __init__(self) -> None:
        super().__init__("Adding this dependency would create a cycle")

class InvalidStatusTransitionError(ValidationError):
    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(f"Invalid status transition: {from_status} -> {to_status}")

class AuthenticationError(DomainException):
    """本人が確かめられない（未ログイン・セッション切れ・IdP 応答の不備）。"""

class AccessDeniedError(DomainException):
    """本人は確かめられたが、このアプリを使わせない（無効化・所属外）。"""

class IdentityProviderUnavailableError(DomainException):
    """IdP に聞けなかった（届かない・5xx・応答が読めない）。

    ⚠ **「誰も居ない」と混ぜない。** 空の名簿として扱うと、IdP が不調なだけで
    全員を止めてしまう。聞けなかったときは何も変えずに見送る。
    """

class MachineNotBoundToApplicationError(DomainException):
    """名乗ったサービスアカウントが、まだ IdP 側でアプリに結び付いていない。

    ⚠ **障害ではなく準備待ち。** 結び付けるまで毎周回ここへ来るので、警告にしない。
    """
