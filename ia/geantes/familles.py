"""Les IA « géantes » (modèles de prévision déjà entraînés par de grands labos), rangées par FAMILLE.

Chaque famille a son propre environnement Python (ses versions de bibliothèques ne gênent pas les autres) et son
propre processus : si une IA plante ou devient trop lente, elle est mise de côté sans bloquer les autres.
Les plus lentes (lot_max) ne prédisent que les premiers marchés de chaque lot, pour tenir dans la minute.
Toutes reçoivent EXACTEMENT la même chose (les 512 derniers prix 1 min, + bougies OHLCV pour Kronos) et
rendent la même chose : la probabilité que le prix soit plus haut dans 1 minute.
"""
FAMILLES = {
    "chronos": {"pip": ["chronos-forecasting>=2.0"],
                "modeles": {"chronos_bolt": "Chronos-Bolt (Amazon, États-Unis)", "chronos2": "Chronos-2 (Amazon, États-Unis)"}},
    "timesfm": {"pip": ["timesfm[torch]"], "lot_max": 12, "modeles": {"timesfm": "TimesFM 2.5 (Google, États-Unis)"}},
    "tirex": {"pip": ["tirex-ts"], "lot_max": 16, "modeles": {"tirex": "TiRex (NXAI, Autriche)"}},
    "toto": {"pip": ["toto-ts", "setuptools<81"], "lot_max": 12, "modeles": {"toto": "Toto (Datadog, États-Unis)"}},
    "moirai": {"pip": ["uni2ts"], "modeles": {"moirai2": "Moirai 2 (Salesforce, États-Unis/Singapour)"}},
    "hf440": {"pip": ["transformers==4.40.1", "accelerate"], "lot_max": 6,
              "modeles": {"sundial": "Sundial (Université Tsinghua, Chine)", "timemoe": "Time-MoE (Chine)"}},
    "kronos": {"pip": ["einops", "huggingface_hub", "safetensors", "pandas", "tqdm"],
               "git": "https://github.com/shiyu-coder/Kronos", "lot_max": 6,
               "modeles": {"kronos": "Kronos (Université Tsinghua, Chine) - spécial bougies de bourse"}},
    "granite": {"pip": ["granite-tsfm"], "modeles": {"ttm": "Granite TinyTimeMixer (IBM)"}},
}

# IA entraînées par nous sur les données Capital.com (ia/predire.py)
MAISON = {
    "logistique": "Régression logistique", "foret": "Forêt aléatoire", "lightgbm": "LightGBM (Microsoft)",
    "catboost": "CatBoost (Yandex, Russie)", "neurones": "Réseau de neurones", "lstm": "LSTM",
    "transformer": "Transformer (style PatchTST)",
}

NOMS = {**MAISON, **{m: n for f in FAMILLES.values() for m, n in f["modeles"].items()},
        "vote": "Vote de toutes les IA", "arbitre": "Vote arbitré (pondéré par les résultats réels)"}
