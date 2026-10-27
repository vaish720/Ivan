"""Signing the Rep in to Microsoft 365 (delegated permissions, one Rep per laptop).

Browser sign-in first, device code as the backup. Tokens are cached in a file
encrypted with Windows DPAPI, so the Rep signs in once.
"""

from pathlib import Path

import msal
from msal_extensions import PersistedTokenCache, build_encrypted_persistence

# offline_access is added by MSAL automatically.
SCOPES = ["User.Read", "Calendars.ReadWrite", "People.Read", "MailboxSettings.Read"]


class GraphAuth:
    def __init__(self, client_id: str, tenant_id: str, cache_path: Path):
        if not client_id or not tenant_id:
            raise RuntimeError("Set ENTRA_CLIENT_ID and ENTRA_TENANT_ID in .env to use CALENDAR_BACKEND=graph.")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache = PersistedTokenCache(build_encrypted_persistence(str(cache_path)))
        self._app = msal.PublicClientApplication(
            client_id, authority=f"https://login.microsoftonline.com/{tenant_id}", token_cache=cache
        )

    def token(self) -> str:
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(SCOPES, account=accounts[0])
            if result and "access_token" in result:
                return result["access_token"]
        try:
            result = self._app.acquire_token_interactive(SCOPES, prompt="select_account")
        except Exception:
            flow = self._app.initiate_device_flow(scopes=SCOPES)
            print(flow["message"], flush=True)
            result = self._app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(f"Microsoft sign-in failed: {result.get('error_description', result)}")
        return result["access_token"]
