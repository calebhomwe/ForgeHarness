"""Lets pytest collect the script-style core-loop tests (python tests/test_core_loop.py
also still works): each test takes a fresh `tmp` directory."""
import pytest


@pytest.fixture
def tmp(tmp_path):
    return tmp_path
