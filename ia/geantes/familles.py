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
    "tirex": {"pip": ["tirex-ts"], "lot_max": 12, "modeles": {"tirex": "TiRex (NXAI, Autriche)"}},
    "toto": {"pip": ["toto-ts", "setuptools<81"], "lot_max": 3, "modeles": {"toto": "Toto (Datadog, États-Unis)"}},
    "moirai": {"pip": ["uni2ts"], "modeles": {"moirai2": "Moirai 2 (Salesforce, États-Unis/Singapour)"}},
    "hf440": {"pip": ["transformers==4.40.1", "accelerate"], "lot_max": 4,
              "modeles": {"sundial": "Sundial (Université Tsinghua, Chine)", "timemoe": "Time-MoE (Chine)"}},
    "kronos": {"pip": ["einops", "huggingface_hub", "safetensors", "pandas", "tqdm"],
               "git": "https://github.com/shiyu-coder/Kronos", "lot_max": 2,
               "modeles": {"kronos": "Kronos (Université Tsinghua, Chine) - spécial bougies de bourse"}},
    "granite": {"pip": ["granite-tsfm"], "modeles": {"ttm": "Granite TinyTimeMixer (IBM)"}},
    "chronos_t5": {"pip": ["chronos-forecasting>=2.0"], "lot_max": 4,
                   "modeles": {"chronos_t5": "Chronos-T5 original (Amazon, États-Unis)"}},
    "timer": {"pip": ["transformers==4.40.1", "accelerate"], "lot_max": 12,
              "modeles": {"timer": "Timer (Université Tsinghua, Chine)"}},
    "lagllama": {"py": "3.10", "pip": ["gluonts[torch]<=0.14.4", "huggingface_hub", "numpy<2", "setuptools<81"],
                 "git": "https://github.com/time-series-foundation-models/lag-llama", "lot_max": 8, "sans_requirements": True,
                 "modeles": {"lagllama": "Lag-Llama (ServiceNow / Mila, Canada)"}},
    # modèles de recherche connus, réentraînés à chaque heure sur les bougies 1 min de ~30 grands marchés
    "nf_a": {"pip": ["neuralforecast"], "entraine": True,
             "modeles": {"nbeats": "N-BEATS (Element AI, Canada)", "nhits": "N-HiTS (Nixtla / CMU)",
                         "tide": "TiDE (Google)", "tcn": "TCN (réseau convolutif)"}},
    "nf_b": {"pip": ["neuralforecast"], "entraine": True,
             "modeles": {"deepar": "DeepAR (Amazon)", "patchtst": "PatchTST (IBM / Princeton)",
                         "tft": "Temporal Fusion Transformer (Google)"}},
}

# Étudiées mais pas branchées (et pourquoi)
EXCLUES = {
    "TimeGPT (Nixtla)": "payant : seulement par leur service en ligne, pas de modèle à télécharger",
    "MOMENT (Carnegie Mellon)": "ne prévoit pas tout seul : il faut le réentraîner pour chaque tâche de prévision",
    "TimesFM 1.0 / 2.0 (Google)": "remplacés par TimesFM 2.5, déjà branché (même famille, en mieux)",
    "TimesFM 3 (Google)": "licence non commerciale et 330 M de paramètres : trop lent sur nos machines gratuites",
    "Toto 2.0 (Datadog)": "pas encore dans la bibliothèque toto-ts utilisée ; Toto 1.0 est branché",
    "Timestral (Mistral, France)": "sorti en octobre 2026, pas encore de bibliothèque Python simple pour le lancer",
    "Informer / Autoformer": "anciens transformers dépassés par PatchTST et TFT, déjà branchés",
}

# IA entraînées par nous sur les données Capital.com (ia/predire.py)
MAISON = {
    "logistique": "Régression logistique", "foret": "Forêt aléatoire", "lightgbm": "LightGBM (Microsoft)",
    "catboost": "CatBoost (Yandex, Russie)", "neurones": "Réseau de neurones", "lstm": "LSTM",
    "transformer": "Transformer (style PatchTST)",
}

NOMS = {**MAISON, **{m: n for f in FAMILLES.values() for m, n in f["modeles"].items()},
        "vote": "Vote de toutes les IA", "arbitre": "Vote arbitré (pondéré par les résultats réels)"}
