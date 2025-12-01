from contextlib import contextmanager

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from config.config_loader import ConfigLoader


class MySQLConnection:
    def __init__(self):
        self.config = ConfigLoader().get_db_config()
        self.db_config = self.config["dbMysql"]
        self.connection_string = self.create_connection_string()
        self.engine = self.create_engine()
        self.test_connection()
        self.Session = sessionmaker(bind=self.engine)

    def create_connection_string(self):
        return f"mysql+pymysql://{self.db_config['user']}:{self.db_config['password']}@{self.db_config['host']}:{self.db_config['port']}/{self.db_config['database']}"

    def create_engine(self):
        return create_engine(
            self.connection_string,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
        )

    def test_connection(self):
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.success("MySQL connection successful.")
        except Exception as e:
            logger.error(f"MySQL connection failed: {e}")
            raise

    @contextmanager
    def get_session(self):
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Session error: {e}")
            raise
        finally:
            session.close()

    def execute_query(self, query, params=None):
        with self.get_session() as session:
            try:
                result = session.execute(text(query), params or {})
                columns = result.keys()
                return [dict(zip(columns, row)) for row in result]
            except Exception as e:
                logger.error(f"Query execution failed: {e}")
                raise

    def execute_query_save(self, query, params=None):
        with self.get_session() as session:
            try:
                result = session.execute(text(query), params or {})
                if result.returns_rows:
                    columns = result.keys()
                    return [dict(zip(columns, row)) for row in result]
                else:
                    session.commit()
                    return None
            except Exception as e:
                session.rollback()
                logger.error(f"Query execution failed: {e}")
                raise

    def execute_transaction(self, operations):
        with self.get_session() as session:
            try:
                for operation in operations:
                    session.execute(
                        text(operation["query"]), operation.get("params", {})
                    )
                session.commit()
            except Exception as e:
                session.rollback()
                logger.error(f"Transaction failed: {e}")
                raise


class MySQLTargetConnection:
    def __init__(self):
        self.config = ConfigLoader().get_db_config()
        self.db_config = self.config["dbMysqlTarget"]
        self.connection_string = self.create_connection_string()
        self.engine = self.create_engine()
        self.test_connection()
        self.Session = sessionmaker(bind=self.engine)

    def create_connection_string(self):
        return f"mysql+pymysql://{self.db_config['user']}:{self.db_config['password']}@{self.db_config['host']}:{self.db_config['port']}/{self.db_config['database']}"

    def create_engine(self):
        return create_engine(
            self.connection_string,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
        )

    def test_connection(self):
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.success("MySQL Target connection successful.")
        except Exception as e:
            logger.error(f"MySQL Target connection failed: {e}")
            raise

    @contextmanager
    def get_session(self):
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Session error: {e}")
            raise
        finally:
            session.close()

    def execute_query(self, query, params=None):
        with self.get_session() as session:
            try:
                result = session.execute(text(query), params or {})
                if result.returns_rows:
                    columns = result.keys()
                    return [dict(zip(columns, row)) for row in result.fetchall()]
                else:
                    return None
            except Exception as e:
                logger.error(f"Query execution failed: {e}")
                raise

    def execute_query_save(self, query, params=None):
        with self.get_session() as session:
            try:
                result = session.execute(text(query), params or {})
                session.commit()
                if result.returns_rows:
                    columns = result.keys()
                    return [dict(zip(columns, row)) for row in result.fetchall()]
                else:
                    return None
            except Exception as e:
                session.rollback()
                logger.error(f"Query execution failed: {e}")
                raise

    def execute_transaction(self, operations):
        with self.get_session() as session:
            try:
                for operation in operations:
                    session.execute(
                        text(operation["query"]), operation.get("params", {})
                    )
                session.commit()
            except Exception as e:
                session.rollback()
                logger.error(f"Transaction failed: {e}")
                raise
