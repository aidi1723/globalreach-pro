from __future__ import annotations

import ctypes
import platform
import shutil
import subprocess
from dataclasses import dataclass, field


class SecretStoreError(Exception):
    pass


class SecretStore:
    def set(self, key: str, value: str) -> None:
        raise NotImplementedError

    def get(self, key: str) -> str:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError


@dataclass
class EphemeralSecretStore(SecretStore):
    _values: dict[str, str] = field(default_factory=dict)

    def set(self, key: str, value: str) -> None:
        self._values[key] = value

    def get(self, key: str) -> str:
        return self._values.get(key, "")

    def delete(self, key: str) -> None:
        self._values.pop(key, None)


class MacOSKeychainSecretStore(SecretStore):
    def __init__(self, service: str = "GlobalReach PRO"):
        self.service = service

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["/usr/bin/security", *args],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except Exception as exc:
            raise SecretStoreError(str(exc)) from exc

    def set(self, key: str, value: str) -> None:
        result = self._run(["add-generic-password", "-U", "-a", key, "-s", self.service, "-w", value])
        if result.returncode != 0:
            raise SecretStoreError(result.stderr.strip() or "macOS Keychain write failed")

    def get(self, key: str) -> str:
        result = self._run(["find-generic-password", "-a", key, "-s", self.service, "-w"])
        if result.returncode != 0:
            return ""
        return result.stdout.rstrip("\n")

    def delete(self, key: str) -> None:
        self._run(["delete-generic-password", "-a", key, "-s", self.service])


class LinuxSecretServiceStore(SecretStore):
    def __init__(self, service: str = "GlobalReach PRO"):
        self.service = service

    def _require_secret_tool(self) -> str:
        binary = shutil.which("secret-tool")
        if not binary:
            raise SecretStoreError("secret-tool is not available")
        return binary

    def set(self, key: str, value: str) -> None:
        binary = self._require_secret_tool()
        result = subprocess.run(
            [binary, "store", "--label", self.service, "service", self.service, "account", key],
            input=value,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode != 0:
            raise SecretStoreError(result.stderr.strip() or "Secret Service write failed")

    def get(self, key: str) -> str:
        binary = self._require_secret_tool()
        result = subprocess.run(
            [binary, "lookup", "service", self.service, "account", key],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.rstrip("\n")

    def delete(self, key: str) -> None:
        binary = self._require_secret_tool()
        subprocess.run(
            [binary, "clear", "service", self.service, "account", key],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )


class WindowsCredentialStore(SecretStore):
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", ctypes.c_uint32),
            ("Type", ctypes.c_uint32),
            ("TargetName", ctypes.c_wchar_p),
            ("Comment", ctypes.c_wchar_p),
            ("LastWritten", ctypes.c_uint64 * 2),
            ("CredentialBlobSize", ctypes.c_uint32),
            ("CredentialBlob", ctypes.c_void_p),
            ("Persist", ctypes.c_uint32),
            ("AttributeCount", ctypes.c_uint32),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", ctypes.c_wchar_p),
            ("UserName", ctypes.c_wchar_p),
        ]

    def __init__(self, service: str = "GlobalReach PRO"):
        self.service = service
        self.advapi32 = ctypes.windll.advapi32

    def _target(self, key: str) -> str:
        return f"{self.service}:{key}"

    def set(self, key: str, value: str) -> None:
        blob = value.encode("utf-16-le")
        blob_buffer = ctypes.create_string_buffer(blob)
        credential = self.CREDENTIALW()
        credential.Type = self.CRED_TYPE_GENERIC
        credential.TargetName = self._target(key)
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(blob_buffer, ctypes.c_void_p)
        credential.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = key
        if not self.advapi32.CredWriteW(ctypes.byref(credential), 0):
            raise SecretStoreError("Windows Credential Manager write failed")

    def get(self, key: str) -> str:
        credential_ptr = ctypes.c_void_p()
        ok = self.advapi32.CredReadW(
            self._target(key),
            self.CRED_TYPE_GENERIC,
            0,
            ctypes.byref(credential_ptr),
        )
        if not ok:
            return ""
        try:
            credential = ctypes.cast(credential_ptr, ctypes.POINTER(self.CREDENTIALW)).contents
            raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            return raw.decode("utf-16-le")
        finally:
            self.advapi32.CredFree(credential_ptr)

    def delete(self, key: str) -> None:
        self.advapi32.CredDeleteW(self._target(key), self.CRED_TYPE_GENERIC, 0)


class ChainedSecretStore(SecretStore):
    def __init__(self, stores: list[SecretStore]):
        self.stores = stores

    def set(self, key: str, value: str) -> None:
        last_error = ""
        for store in self.stores:
            try:
                store.set(key, value)
                return
            except Exception as exc:
                last_error = str(exc)
        raise SecretStoreError(last_error or "No secret store is available")

    def get(self, key: str) -> str:
        for store in self.stores:
            try:
                value = store.get(key)
            except Exception:
                continue
            if value:
                return value
        return ""

    def delete(self, key: str) -> None:
        for store in self.stores:
            try:
                store.delete(key)
            except Exception:
                continue


def create_default_secret_store() -> SecretStore:
    stores: list[SecretStore] = []
    system = platform.system()
    if system == "Darwin" and _executable_exists("/usr/bin/security"):
        stores.append(MacOSKeychainSecretStore())
    elif system == "Windows":
        stores.append(WindowsCredentialStore())
    elif system == "Linux":
        stores.append(LinuxSecretServiceStore())
    stores.append(EphemeralSecretStore())
    return ChainedSecretStore(stores)


def _executable_exists(path: str) -> bool:
    return shutil.which(path) == path or shutil.which(path) is not None
