-- FOX MLO Database Initialization
-- Extensions & initial database configuration

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$
BEGIN
    RAISE NOTICE 'FOX MLO PostgreSQL Database initialized successfully.';
END $$;
