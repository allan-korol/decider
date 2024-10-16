from . import akas, attack, cart, coocs, mismaps, role, user, util, mitigation

from textwrap import dedent as txt_dedent
from sqlalchemy.sql import text as sql_text, quoted_name as sql_quoted_name

from app.models import db
from app.utils.db.util import messaged_timer
from app.utils.db.saltstack_scram_sha_256 import scram_sha_256
from app.env_vars import DB_DATABASE, DB_KIOSK_NAME, DB_KIOSK_PASS, DB_ADMIN_NAME, DB_ADMIN_PASS


@messaged_timer("Creating Extensions / FTS Dictionary")
def extensions_dictionary():
    query = txt_dedent(
        """
        -- Used for top-right Technique search - WORD_SIMILARITY()
        CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;

        -- fake mutable unaccent function for full search
        CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA public;
        DROP FUNCTION IF EXISTS imm_unaccent;
        CREATE FUNCTION imm_unaccent(text) RETURNS text AS $$
        BEGIN
            RETURN unaccent($1);
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;

        -- Dictionary for Full Search, doesn't remove stop words "a", "the", ..
        DROP TEXT SEARCH CONFIGURATION IF EXISTS english_nostop;
        DROP TEXT SEARCH DICTIONARY IF EXISTS english_stem_nostop;
        CREATE TEXT SEARCH DICTIONARY english_stem_nostop (template = snowball, language = english);
        CREATE TEXT SEARCH CONFIGURATION english_nostop (copy = english);
        ALTER TEXT SEARCH CONFIGURATION english_nostop ALTER MAPPING REPLACE english_stem WITH english_stem_nostop;
        """
    )
    db.session.execute(query)
    db.session.commit()


@messaged_timer("Creating Kiosk User (Limited Access)")
def kiosk_user():
    create_user(DB_KIOSK_NAME, DB_KIOSK_PASS)

def create_user(username, password):
    query = txt_dedent(
        """
        -- (Re)Create User
        DO
        LANGUAGE plpgsql
        $do$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :db_user_name_str) THEN
                REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {db_user_name};
                REVOKE USAGE ON SCHEMA public FROM {db_user_name};
                REVOKE CONNECT ON DATABASE decider FROM {db_user_name};
                DROP USER {db_user_name};
            END IF;
        END
        $do$;
        CREATE USER {db_user_name} WITH NOINHERIT LOGIN PASSWORD :db_user_pass;

        -- Modify Their Permissions
        REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {db_user_name};
        REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {db_user_name};

        GRANT CONNECT ON DATABASE {db_database} TO {db_user_name};
        GRANT USAGE ON SCHEMA public TO {db_user_name};

        GRANT SELECT ON attack_version_platform_map TO {db_user_name};
        GRANT SELECT ON tactic_platform_map TO {db_user_name};
        GRANT SELECT ON technique_platform_map TO {db_user_name};
        GRANT SELECT ON tactic_technique_map TO {db_user_name};
        GRANT SELECT ON technique_aka_map TO {db_user_name};
        GRANT SELECT ON tactic_ds_map TO {db_user_name};
        GRANT SELECT ON technique_ds_map TO {db_user_name};
        GRANT SELECT ON technique_dc_map TO {db_user_name};
        GRANT SELECT ON attack_version TO {db_user_name};
        GRANT SELECT ON platform TO {db_user_name};
        GRANT SELECT ON tactic TO {db_user_name};
        GRANT SELECT ON technique TO {db_user_name};
        GRANT SELECT ON aka TO {db_user_name};
        GRANT SELECT ON blurb TO {db_user_name};
        GRANT SELECT ON mismapping TO {db_user_name};
        GRANT SELECT ON co_occurrence TO {db_user_name};
        GRANT SELECT ON data_source TO {db_user_name};
        GRANT SELECT ON data_component TO {db_user_name};
        GRANT SELECT ON mitigation TO {db_user_name};
        GRANT SELECT ON mitigation_source TO {db_user_name};
        GRANT SELECT ON technique_mitigation_map TO {db_user_name};
        """
    )
    query = query.format(
        db_database=sql_quoted_name(DB_DATABASE, False),
        db_user_name=sql_quoted_name(username, False),
    )
    query = sql_text(query).bindparams(
        db_user_name_str=username,
        db_user_pass=scram_sha_256(password),
    )

    db.session.execute(query)
    db.session.commit()


@messaged_timer("Adding tables to DB")
def all_tables():
    db.create_all()
    db.session.commit()
