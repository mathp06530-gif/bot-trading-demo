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
def sans_elan_par_defaut(monkeypatch):
    """Les anciens tests ne voient pas la stratégie expérimentale « Élan » (testée à part)."""
    from bot import elan
    monkeypatch.setattr(elan, "LISTE", [])


@pytest.fixture(autouse=True)
def sans_supertrend_par_defaut(monkeypatch):
    """Les anciens tests ne voient pas la stratégie expérimentale « Supertrend » (testée à part)."""
    from bot import supertrend
    monkeypatch.setattr(supertrend, "LISTE", [])


@pytest.fixture(autouse=True)
def tendance_btc_pour_les_tests(monkeypatch):
    """Bitcoin est retiré en vrai (MARCHES="" depuis le 26/11/2026), mais les anciens tests gardent
    la Tendance 4 h sur BTCUSD pour vérifier que son code marche toujours si on la relance."""
    from bot import main
    monkeypatch.setattr(main, "MARCHES", ["BTCUSD"])


@pytest.fixture(autouse=True)
def graphiques_ailleurs(monkeypatch, tmp_path):
    """Les tests n'écrivent jamais dans docs/graphiques/ du dépôt."""
    from bot import graphiques
    monkeypatch.setattr(graphiques, "DOSSIER", tmp_path / "graphiques")


@pytest.fixture(autouse=True)
def veille_hors_ligne(monkeypatch):
    """Les tests n'appellent jamais Yahoo ni Nasdaq."""
    from bot import veille
    monkeypatch.setattr(veille, "_titres", lambda s: [])
