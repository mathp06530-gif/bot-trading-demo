import pytest


@pytest.fixture(autouse=True)
def pas_d_internet(monkeypatch):
    """Les tests n'appellent jamais le vrai calendrier économique : semaine sans annonce."""
    from bot import actualites
    monkeypatch.setattr(actualites, "_lire_calendrier", lambda: [])


@pytest.fixture(autouse=True)
def sans_cassure_par_defaut(monkeypatch):
    """Les anciens tests ne voient pas la stratégie cassure (testée à part)."""
    from bot import main
    monkeypatch.setattr(main, "MARCHES_CASSURE", [])


@pytest.fixture(autouse=True)
def sans_filtre_bollinger(monkeypatch):
    """Les anciens tests de la stratégie rapide ne voient pas le filtre Bollinger (testé à part)."""
    from bot import rapide
    monkeypatch.setattr(rapide, "FILTRE_BOLLINGER", False)


@pytest.fixture(autouse=True)
def sans_tendance_mois_par_defaut(monkeypatch):
    """Les anciens tests ne voient pas la stratégie tendance 1 mois (testée à part)."""
    from bot import tendance_mois
    monkeypatch.setattr(tendance_mois, "LISTE", [])
