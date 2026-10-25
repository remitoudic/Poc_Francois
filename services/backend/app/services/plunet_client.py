"""
Plunet BusinessManager SOAP API Client
Target Base URL: https://portal.foxtranslations.com/
Compatible with Plunet BusinessManager 10.x+
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional
from urllib.parse import urljoin

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from zeep import Client
from zeep.exceptions import Fault


class PlunetAPIError(Exception):
    """Exception raised for Plunet API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, raw_response: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.raw_response = raw_response


class PlunetAuthenticationError(PlunetAPIError):
    """Exception raised when authentication fails."""
    pass


class PlunetClient:
    """Client for interacting with the Plunet BusinessManager SOAP Web Services API."""

    DEFAULT_BASE_URL = "https://portal.foxtranslations.com"

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        auto_login: bool = False,
    ):
        """
        Initialize the Plunet client.

        :param base_url: Base URL of the Plunet portal (defaults to https://portal.foxtranslations.com)
        :param username: API Username (can also be set via PLUNET_USERNAME env var)
        :param password: API Password (can also be set via PLUNET_PASSWORD env var)
        :param auto_login: If True and credentials are provided, login immediately
        """
        raw_url = base_url or os.getenv("PLUNET_BASE_URL", self.DEFAULT_BASE_URL)
        self.base_url = raw_url.rstrip("/") + "/"
        self.username = username or os.getenv("PLUNET_USERNAME")
        self.password = password or os.getenv("PLUNET_PASSWORD")
        self.uuid: Optional[str] = None

        # Cache for lazy-initialized Zeep clients
        self._clients: Dict[str, Client] = {}

        if auto_login and self.username and self.password:
            self.login()

    def _get_wsdl_url(self, service_name: str) -> str:
        """Construct full WSDL URL for a given Plunet service."""
        return urljoin(self.base_url, f"{service_name}?wsdl")

    def get_service(self, service_name: str) -> Any:
        """
        Get or initialize the Zeep client service for a specific Plunet WSDL endpoint.
        Example service names: 'PlunetAPI', 'DataCustomer30', 'DataOrder30', etc.
        """
        if service_name not in self._clients:
            wsdl_url = self._get_wsdl_url(service_name)
            client = Client(wsdl=wsdl_url)
            self._clients[service_name] = client
        return self._clients[service_name].service

    # --- Convenience Service Accessors ---

    @property
    def auth_service(self) -> Any:
        """Main PlunetAPI service (login, logout, version)."""
        return self.get_service("PlunetAPI")

    @property
    def customer_service(self) -> Any:
        """DataCustomer30 service."""
        return self.get_service("DataCustomer30")

    @property
    def order_service(self) -> Any:
        """DataOrder30 service."""
        return self.get_service("DataOrder30")

    @property
    def quote_service(self) -> Any:
        """DataQuote30 service."""
        return self.get_service("DataQuote30")

    @property
    def item_service(self) -> Any:
        """DataItem30 service."""
        return self.get_service("DataItem30")

    @property
    def job_service(self) -> Any:
        """DataJob30 service."""
        return self.get_service("DataJob30")

    @property
    def resource_service(self) -> Any:
        """DataResource30 service."""
        return self.get_service("DataResource30")

    @property
    def admin_service(self) -> Any:
        """DataAdmin30 service."""
        return self.get_service("DataAdmin30")

    @property
    def document_service(self) -> Any:
        """DataDocument30 service."""
        return self.get_service("DataDocument30")

    # --- Authentication & Session Management ---

    def get_version(self) -> str:
        """
        Get Plunet server version without requiring authentication.
        """
        res = self.auth_service.getPlunetVersion()
        return self.unwrap_response(res)

    def login(self, username: Optional[str] = None, password: Optional[str] = None) -> str:
        """
        Authenticate with Plunet and obtain a session UUID token.
        """
        user = username or self.username
        pwd = password or self.password

        if not user or not pwd:
            raise PlunetAuthenticationError(
                "Username and password are required. Provide them as arguments or set "
                "PLUNET_USERNAME and PLUNET_PASSWORD environment variables."
            )

        token = self.auth_service.login(user, pwd)

        if not token or token == "refused":
            raise PlunetAuthenticationError(
                f"Plunet login failed for user '{user}'. Response: {token}"
            )

        self.uuid = token
        self.username = user
        self.password = pwd
        return self.uuid

    def logout(self) -> None:
        """Terminate the active Plunet session."""
        if self.uuid:
            try:
                self.auth_service.logout(self.uuid)
            except Exception:
                pass
            finally:
                self.uuid = None

    def validate_session(self) -> bool:
        """Validate if the current session UUID is still valid."""
        if not self.uuid or not self.username or not self.password:
            return False
        try:
            res = self.auth_service.validate(self.uuid, self.username, self.password)
            return bool(res and getattr(res, "statusCode", -1) == 0)
        except Exception:
            return False

    def require_session(self) -> str:
        """Return the current session UUID or raise an error if not logged in."""
        if not self.uuid:
            raise PlunetAuthenticationError(
                "No active Plunet session. Call client.login() first."
            )
        return self.uuid

    # --- Response Handling ---

    @staticmethod
    def unwrap_response(result: Any) -> Any:
        """
        Plunet methods return a Result structure:
        {
            'statusCode': 0,
            'statusMessage': 'OK',
            'data': <payload>
        }
        This helper checks statusCode and returns data or raises PlunetAPIError.
        """
        if result is None:
            return None

        # Check for standard Plunet Result objects
        if hasattr(result, "statusCode"):
            status_code = getattr(result, "statusCode")
            status_message = getattr(result, "statusMessage", "")
            if status_code != 0:
                raise PlunetAPIError(
                    f"Plunet API error ({status_code}): {status_message}",
                    status_code=status_code,
                    raw_response=result,
                )
            if hasattr(result, "data"):
                return getattr(result, "data")
            return result

        return result

    # --- Context Manager Support ---

    def __enter__(self) -> "PlunetClient":
        if self.username and self.password and not self.uuid:
            self.login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.logout()
