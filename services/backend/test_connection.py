#!/usr/bin/env python3
"""
Test connection script for Plunet BusinessManager API
Endpoint: https://portal.foxtranslations.com/
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Search for .env in current directory and parent directories (root)
for env_path in [Path.cwd() / ".env", Path(__file__).resolve().parent / ".env", Path(__file__).resolve().parent.parent.parent / ".env"]:
    if env_path.exists():
        load_dotenv(env_path)
        break

from plunet_client import PlunetClient, PlunetAPIError, PlunetAuthenticationError


def main():
    print("=" * 60)
    print("Plunet API Connection Test")
    print("Target: https://portal.foxtranslations.com/")
    print("=" * 60)

    # 1. Initialize client
    client = PlunetClient()
    print(f"\n[1] Initialized client with Base URL: {client.base_url}")

    # 2. Test server version (does not require login credentials)
    print("[2] Fetching Plunet server version via SOAP...")
    try:
        version = client.get_version()
        print(f" -> SUCCESS! Plunet Server Version: {version}")
    except Exception as e:
        print(f" -> FAILED to fetch version: {e}")
        sys.exit(1)

    # 3. Check credentials for authenticated operations
    username = os.getenv("PLUNET_USERNAME")
    password = os.getenv("PLUNET_PASSWORD")

    if not username or not password:
        print("\n" + "-" * 60)
        print("Note: PLUNET_USERNAME and PLUNET_PASSWORD are not set.")
        print("To test authenticated requests (e.g. orders, customers):")
        print("  1. Copy env.example to .env:  cp env.example .env")
        print("  2. Add your API user credentials to .env")
        print("  3. Run this script again:     python3 test_connection.py")
        print("-" * 60)
        print("\nBasic connection to Fox Translations Plunet API verified successfully!")
        return

    # 4. Attempt login with provided credentials
    print(f"\n[3] Attempting login for API user '{username}'...")
    try:
        uuid = client.login()
        print(f" -> SUCCESS! Received session UUID: {uuid}")

        # 5. Example API query using active session
        print("\n[4] Querying customer service info...")
        try:
            # Plunet provides methods like getAllCustomerObjects, etc.
            # Example: call getAvailablePaymentMethodList or similar lightweight method
            pm_res = client.customer_service.getAvailablePaymentMethodList(uuid)
            pm_list = client.unwrap_response(pm_res)
            print(f" -> Payment methods retrieved: {pm_list}")
        except PlunetAPIError as pe:
            print(f" -> API call error: {pe}")

    except PlunetAuthenticationError as ae:
        print(f" -> Authentication failed: {ae}")
    finally:
        client.logout()
        print("\n[5] Session closed gracefully.")


if __name__ == "__main__":
    main()
