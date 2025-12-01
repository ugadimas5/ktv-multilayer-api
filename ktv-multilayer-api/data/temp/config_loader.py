import os
from pathlib import Path

from dotenv import load_dotenv

envPath = Path(".") / ".env"
load_dotenv(dotenv_path=envPath)


class ConfigLoader:
    def __init__(self):
        self.config = self.load_config()

    def get_mysql_config(self):
        is_dev = os.getenv("APP_ENV") == "development"
        env_prefix = "" if is_dev else "PROD_"

        return {
            "host": os.getenv(f"DB_MYSQL_{env_prefix}HOST"),
            "user": os.getenv(f"DB_MYSQL_{env_prefix}USER"),
            "password": os.getenv(f"DB_MYSQL_{env_prefix}PASSWORD"),
            "database": os.getenv(f"DB_MYSQL_{env_prefix}DATABASE"),
            "port": int(os.getenv(f"DB_MYSQL_{env_prefix}PORT")),
        }

    def load_config(self):
        config = {
            "app": {
                "name": os.getenv("APP_NAME"),
                "version": os.getenv("APP_VERSION"),
                "environment": os.getenv("APP_ENV"),
                "port": int(os.getenv("APP_PORT")),
                "prefix": {"apiV1": os.getenv("APP_PREFIX_API_V1")},
                "api_key": os.getenv("API_KEY"),
                "aws_access_key": os.getenv("AWS_ACCESS_KEY_ID"),
                "aws_secret_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
                "satelligence_url": os.getenv("SATELLIGENCE_URL"),
                "satelligence_bearer_token": os.getenv("SATELLIGENCE_BEARER_TOKEN"),
                "koltigis_api_url": os.getenv("KOLTIGIS_API_URL"),
                "callback_polygon_validation_url": os.getenv(
                    "CALLBACK_POLYGON_VALIDATION_URL"
                ),
                "ee_service_account_path": os.getenv("EE_SERVICE_ACCOUNT_PATH"),
                "callback_to_partner_report_url": os.getenv(
                    "CALLBACK_TO_PARTNER_REPORT_URL"
                ),
            },
            "db": {
                "dbMysql": self.get_mysql_config(),
                "dbMysqlTarget": {
                    "host": os.getenv("DB_MYSQL_TARGET_HOST"),
                    "user": os.getenv("DB_MYSQL_TARGET_USER"),
                    "password": os.getenv("DB_MYSQL_TARGET_PASSWORD"),
                    "database": os.getenv("DB_MYSQL_TARGET_DATABASE"),
                    "port": int(os.getenv("DB_MYSQL_TARGET_PORT")),
                },
                "dbPgsql": {
                    "host": os.getenv("DB_PGSQL_HOST"),
                    "user": os.getenv("DB_PGSQL_USER"),
                    "password": os.getenv("DB_PGSQL_PASSWORD"),
                    "database": os.getenv("DB_PGSQL_DATABASE"),
                    "port": int(os.getenv("DB_PGSQL_PORT")),
                },
                "dbPgsqlOld": {
                    "host": os.getenv("DB_PGSQL_OLD_HOST"),
                    "user": os.getenv("DB_PGSQL_OLD_USER"),
                    "password": os.getenv("DB_PGSQL_OLD_PASSWORD"),
                    "database": os.getenv("DB_PGSQL_OLD_DATABASE"),
                    "port": int(os.getenv("DB_PGSQL_OLD_PORT")),
                },
                "dbRedshift": {
                    "host": os.getenv("DB_REDSHIFT_HOST"),
                    "user": os.getenv("DB_REDSHIFT_USER"),
                    "password": os.getenv("DB_REDSHIFT_PASSWORD"),
                    "database": os.getenv("DB_REDSHIFT_DATABASE"),
                    "port": int(os.getenv("DB_REDSHIFT_PORT")),
                },
            },
            "opensearch": {
                "host": os.getenv("OPENSEARCH_HOST"),
                "port": int(os.getenv("OPENSEARCH_PORT")),
                "user": os.getenv("OPENSEARCH_USER"),
                "password": os.getenv("OPENSEARCH_PASSWORD"),
                "index": os.getenv("OPENSEARCH_INDEX"),
            },
        }
        return config

    def get_db_config(self):
        return self.config["db"]

    def get_app_config(self):
        return self.config["app"]

    def get_opensearch_config(self):
        return self.config["opensearch"]
