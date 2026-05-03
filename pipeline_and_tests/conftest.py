"""Shared pytest fixtures for the data quality test suite."""

from __future__ import annotations

import os

import pytest
from google.cloud import bigquery

PROJECT = os.environ.get("BQ_PROJECT", "panw-gcs-northstar")
DATASET = os.environ.get("BQ_DATASET", "gcs_north_star")


@pytest.fixture(scope="session")
def bq() -> bigquery.Client:
    """A single BigQuery client shared across the test session."""
    return bigquery.Client(project=PROJECT)


@pytest.fixture(scope="session")
def fq():
    """Helper to build fully-qualified table names."""
    def _fq(table: str) -> str:
        return f"`{PROJECT}.{DATASET}.{table}`"
    return _fq


def scalar(client: bigquery.Client, sql: str):
    """Execute a query expected to return a single scalar value."""
    rows = list(client.query(sql).result())
    if not rows:
        return None
    return rows[0][0]


def count(client: bigquery.Client, sql: str) -> int:
    """Execute a query whose first column should be an integer count."""
    v = scalar(client, sql)
    return int(v) if v is not None else 0
