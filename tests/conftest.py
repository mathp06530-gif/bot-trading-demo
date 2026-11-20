import pytest


@pytest.fixture(autouse=True)
def pas_d_internet(monkeypatch):
    """Les tests n'appellent jamais le vrai calendrier économique : semaine sans annonce."""
    from bot import actualites
    monkeypatch.setattr(actualites, "_lire_calendrier", lambda: [])
