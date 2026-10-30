"""Point the app at a separate test database before anything imports app.database."""

import os

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://fox_user:fox_password@localhost:5433/fox_mlo_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
