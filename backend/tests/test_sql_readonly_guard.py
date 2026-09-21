"""Regression: run_query must reject write/DDL/filesystem SQL."""
import pytest

from backend.mcp.data_access import _assert_read_only_sql


@pytest.mark.parametrize(
    "query",
    [
        "DROP TABLE products",
        "DELETE FROM products",
        "COPY products TO '/tmp/x.csv'",
        "ATTACH 'other.db' AS other",
        "SELECT 1; DROP TABLE products",
        "INSERT INTO products VALUES (1)",
        "CREATE TABLE t(x INT)",
        "EXPORT DATABASE '/tmp/db'",
        "SELECT COUNT(*) FROM read_csv('/etc/passwd')",
        "SELECT * FROM read_csv_auto('/tmp/x.csv')",
        "SELECT * FROM parquet_scan('/tmp/x.parquet')",
        "SELECT * FROM glob('/etc/*')",
    ],
)
def test_assert_read_only_rejects_dangerous(query):
    with pytest.raises(PermissionError):
        _assert_read_only_sql(query)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT id, name FROM products LIMIT 10",
        "WITH x AS (SELECT 1 AS n) SELECT n FROM x",
        "select count(*) as cnt from orders",
    ],
)
def test_assert_read_only_allows_select(query):
    _assert_read_only_sql(query)
