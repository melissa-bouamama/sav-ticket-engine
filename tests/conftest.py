"""Fixtures communes : chemins des petits fichiers d'exemple."""

from pathlib import Path

import pytest

DONNEES = Path(__file__).resolve().parents[1] / "donnees"


@pytest.fixture
def chemin_exemple() -> Path:
    return DONNEES / "exemple_tickets.jsonl"


@pytest.fixture
def chemin_agents() -> Path:
    return DONNEES / "exemple_agents.csv"
