

#!/usr/bin/env python3
"""
Tests for Airflow DAG integrity.

This module contains tests to ensure our DAGs load and have a valid structure.
"""

import os
import logging
import unittest
from pathlib import Path
from airflow.models import DagBag

# Get DAGs directory
DAGS_DIR = Path(__file__).parents[1] / "dags"


class TestDagIntegrity(unittest.TestCase):
    """Test DAG integrity."""

    @classmethod
    def setUpClass(cls):
        """Set up test class."""
        cls.dagbag = DagBag(dag_folder=str(DAGS_DIR), include_examples=False)

    def test_no_import_errors(self):
        """Test there are no import errors in our DAGs."""
        import_errors = self.dagbag.import_errors
        self.assertEqual(
            len(import_errors), 0, f"DAG import errors: {import_errors}"
        )

    def test_all_dags_have_required_fields(self):
        """Test that all DAGs have the required fields."""
        for dag_id, dag in self.dagbag.dags.items():
            self.assertIsNotNone(dag.default_args.get('owner', None),
                                f"{dag_id}: Missing owner in default_args")
            self.assertIsNotNone(dag.default_args.get('retries', None),
                                f"{dag_id}: Missing retries in default_args")
            self.assertIsNotNone(dag.default_args.get('retry_delay', None),
                                f"{dag_id}: Missing retry_delay in default_args")

    def test_all_dags_have_tags(self):
        """Test that all DAGs have tags."""
        for dag_id, dag in self.dagbag.dags.items():
            tags = dag.tags
            self.assertTrue(
                len(tags) > 0, f"{dag_id}: No tags specified for DAG"
            )


if __name__ == '__main__':
    unittest.main() 
