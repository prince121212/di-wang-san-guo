"""Platform ports; implementations live in desktop or Android hosts."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional, Protocol


class CredentialPort(Protocol):
    def load_password(self, account_ref: str) -> Optional[str]:
        ...

    def delete(self, account_ref: str) -> None:
        ...


class DataDirectoryPort(Protocol):
    def data_directory(self) -> Path:
        ...


class PlatformEventPort(Protocol):
    def publish(self, event: Mapping[str, object]) -> None:
        ...
