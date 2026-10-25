#!/usr/bin/env python3
"""
Example operations using PlunetClient and pyplunet with Fox Translations Plunet API
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Search for .env in current and parent directories
for env_path in [Path.cwd() / ".env", Path(__file__).resolve().parent / ".env", Path(__file__).resolve().parent.parent.parent / ".env"]:
    if env_path.exists():
        load_dotenv(env_path)
        break

from plunet_client import PlunetClient, PlunetAPIError

# Configuration
BASE_URL = os.getenv("PLUNET_BASE_URL", "https://portal.foxtranslations.com")
USERNAME = os.getenv("PLUNET_USERNAME", "your_username")
PASSWORD = os.getenv("PLUNET_PASSWORD", "your_password")


def example_with_plunet_client():
    """Example using the custom PlunetClient (Zeep SOAP wrapper)."""
    print("\n=== Example 1: PlunetClient with Context Manager ===")

    # Using context manager automatically logs in (if creds given) and logs out upon exit
    with PlunetClient(base_url=BASE_URL, username=USERNAME, password=PASSWORD) as client:
        # Check server version (no auth needed)
        version = client.get_version()
        print(f"Plunet Version: {version}")

        # Check if authenticated
        if not client.uuid:
            print("Skipping authenticated calls (set PLUNET_USERNAME and PLUNET_PASSWORD).")
            return

        uuid = client.uuid
        print(f"Logged in with UUID: {uuid}")

        # 1. Customers: Get available payment methods or customer list
        try:
            res = client.customer_service.getAvailablePaymentMethodList(uuid)
            payment_methods = client.unwrap_response(res)
            print("Payment Methods:", payment_methods)
        except PlunetAPIError as e:
            print(f"Customer service error: {e}")

        # 2. Orders: Query order details
        try:
            # Example: Retrieve an order object by ID (replace 12345 with a valid ID)
            sample_order_id = 12345
            # res = client.order_service.getOrderObject(uuid, sample_order_id)
            # order = client.unwrap_response(res)
            # print("Order Details:", order)
        except PlunetAPIError as e:
            print(f"Order query error: {e}")


def example_with_pyplunet():
    """Alternative example using the community `pyplunet` library."""
    print("\n=== Example 2: Using pyplunet Library ===")
    try:
        from pyplunet import PlunetClient as PyPlunetClient

        client = PyPlunetClient(base_url=BASE_URL)
        print("Initialized pyplunet client.")

        if USERNAME and USERNAME != "your_username":
            client.login(username=USERNAME, password=PASSWORD)
            print("Logged in via pyplunet.")
            print(f"Active UUID: {client.uuid}")
            print(f"Plunet Version: {client.plunet_version}")
            client.logout()
            print("Logged out via pyplunet.")
        else:
            print("Set valid credentials to run pyplunet authenticated calls.")
    except Exception as e:
        print(f"pyplunet error: {e}")


if __name__ == "__main__":
    example_with_plunet_client()
    example_with_pyplunet()
