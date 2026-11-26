"""Processus d'UNE famille d'IA géantes (lancé dans l'environnement Python de la famille).

Protocole (une ligne JSON par demande, sur l'entrée standard) :
  {"entree": "x.npz", "sortie": "y.npz", "H": 1}
  x.npz contient "prix" (n, L) = derniers prix moyens, et "ohlcv" (n, L, 5) = bougies 1 min.
Réponse (une ligne JSON sur la sortie d'origine) : {"ok": {...modèle: secondes}, "erreurs": {...}}
  y.npz contient, pour chaque modèle qui a répondu, la probabilité de hausse à H minutes (n,).
Usage : python travailleur.py <famille> <dossier_du_depot>
"""
import json
import math
import os
import sys
import time
import traceback

import numpy as np

FAMILLE = sys.argv[1]
DEPOT = sys.argv[2]
sys.path.insert(0, DEPOT)
from ia.geantes.familles import FAMILLES  # noqa: E402

VRAIE_SORTIE = os.fdopen(os.dup(1), "w")
os.dup2(2, 1)  # les bibliothèques qui écrivent n'importe quoi vont dans le journal, pas dans le protocole
sys.stdout = sys.stderr

import torch  # noqa: E402

torch.set_num_threads(max(1, int(os.getenv("IA_FILS", "1"))))
NIVEAUX = [round(x, 1) for x in np.linspace(0.1, 0.9, 9)]


def depuis_quantiles(q, dernier):
    """q (n, 9) : quantiles 10 %..90 % du prix prévu -> probabilité que le prix finisse plus haut que `dernier`."""
    q = np.sort(np.asarray(q, dtype=float), axis=1)
    return np.array([1 - np.interp(dernier[k], q[k], NIVEAUX, left=0.05, right=0.95) for k in range(len(q))])


def depuis_echantillons(s, dernier):
    """s (n, S) : prix simulés -> part des simulations au-dessus du dernier prix (bornée 2 %..98 %)."""
    s = np.asarray(s, dtype=float)
    return np.clip(((s > dernier[:, None]).sum(1) + 0.5 * (s == dernier[:, None]).sum(1)) / s.shape[1], 0.02, 0.98)


def depuis_point(pred, prix):
    """Prévision unique -> probabilité, selon l'écart rapporté au mouvement habituel d'une minute."""
    dernier = prix[:, -1]
    sigma = np.std(np.diff(prix[:, -61:], axis=1), axis=1) + 1e-12
    return 0.5 + 0.5 * np.tanh((np.asarray(pred, dtype=float) - dernier) / sigma)


def normer(prix):
    m = prix.mean(1, keepdims=True)
    s = prix.std(1, keepdims=True) + 1e-9
    return (prix - m) / s, m, s


# --------------------------------------------------------------------------- chargement + prévision par modèle
def charger(nom):
    if nom == "chronos_bolt":
        from chronos import BaseChronosPipeline
        return BaseChronosPipeline.from_pretrained("amazon/chronos-bolt-small", device_map="cpu", torch_dtype=torch.float32)
    if nom == "chronos2":
        from chronos import BaseChronosPipeline
        return BaseChronosPipeline.from_pretrained("amazon/chronos-2", device_map="cpu")
    if nom == "timesfm":
        import timesfm
        m = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch", torch_compile=False)
        m.compile(timesfm.ForecastConfig(max_context=512, max_horizon=16, normalize_inputs=True, per_core_batch_size=4,
                                         use_continuous_quantile_head=True, force_flip_invariance=True,
                                         infer_is_positive=True, fix_quantile_crossing=True))
        return m
    if nom == "tirex":
        from tirex import load_model
        try:
            return load_model("NX-AI/TiRex", backend="torch")
        except TypeError:
            return load_model("NX-AI/TiRex")
    if nom == "toto":
        from toto.inference.forecaster import TotoForecaster
        from toto.model.toto import Toto
        t = Toto.from_pretrained("Datadog/Toto-Open-Base-1.0")
        t.eval()
        return TotoForecaster(t.model)
    if nom == "moirai2":
        from uni2ts.model.moirai2 import Moirai2Module
        return Moirai2Module.from_pretrained("Salesforce/moirai-2.0-R-small")
    if nom == "sundial":
        from transformers import AutoModelForCausalLM
        return AutoModelForCausalLM.from_pretrained("thuml/sundial-base-128m", trust_remote_code=True)
    if nom == "timemoe":
        from transformers import AutoModelForCausalLM
        return AutoModelForCausalLM.from_pretrained("Maple728/TimeMoE-50M", device_map="cpu", trust_remote_code=True)
    if nom == "kronos":
        sys.path.insert(0, os.path.join(DEPOT, "ia", "vendor", "kronos"))
        from model import Kronos, KronosPredictor, KronosTokenizer
        tok = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
        mod = Kronos.from_pretrained("NeoQuasar/Kronos-small")
        return KronosPredictor(mod, tok, device="cpu", max_context=512)
    if nom == "ttm":
        from tsfm_public.toolkit.get_model import get_model
        return get_model("ibm-granite/granite-timeseries-ttm-r2", context_length=512, prediction_length=96)
    if nom == "chronos_t5":
        from chronos import BaseChronosPipeline
        return BaseChronosPipeline.from_pretrained("amazon/chronos-t5-small", device_map="cpu", torch_dtype=torch.float32)
    if nom == "timer":
        from transformers import AutoModelForCausalLM
        return AutoModelForCausalLM.from_pretrained("thuml/timer-base-84m", trust_remote_code=True)
    if nom == "lagllama":
        sys.path.insert(0, os.path.join(DEPOT, "ia", "vendor", "lagllama"))
        from huggingface_hub import hf_hub_download
        from lag_llama.gluon.estimator import LagLlamaEstimator
        ckpt = hf_hub_download("time-series-foundation-models/Lag-Llama", "lag-llama.ckpt")
        a = torch.load(ckpt, map_location="cpu", weights_only=False)["hyper_parameters"]["model_kwargs"]
        est = LagLlamaEstimator(ckpt_path=ckpt, prediction_length=1, context_length=32, input_size=a["input_size"],
                                n_layer=a["n_layer"], n_embd_per_head=a["n_embd_per_head"], n_head=a["n_head"],
                                scaling=a["scaling"], time_feat=a["time_feat"], batch_size=64, num_parallel_samples=20,
                                device=torch.device("cpu"))
        return est.create_predictor(est.create_transformation(), est.create_lightning_module())
    if FAMILLE in ("nf_a", "nf_b"):
        return entrainer_nf()
    raise ValueError(nom)


_NF = {}


def entrainer_nf():
    """Entraîne une seule fois tous les modèles de la famille sur les bougies 1 min fournies par le chef d'orchestre."""
    if "nf" in _NF:
        return _NF["nf"]
    import logging
    import warnings
    import pandas as pd
    warnings.filterwarnings("ignore")
    for n in ("pytorch_lightning", "lightning", "lightning.pytorch"):
        logging.getLogger(n).setLevel(logging.ERROR)
    from neuralforecast import NeuralForecast
    from neuralforecast import models as M
    d = np.load(os.environ["IA_ENTRAINEMENT"], allow_pickle=True)
    df = pd.concat([pd.DataFrame({"unique_id": f"s{k}", "ds": np.arange(len(x)), "y": np.asarray(x, dtype=float)})
                    for k, x in enumerate(d["series"]) if len(x) > 200])
    kw = dict(h=2, input_size=64, max_steps=int(os.getenv("IA_NF_PAS", "80")), scaler_type="standard", batch_size=64,
              enable_progress_bar=False, enable_model_summary=False, logger=False, accelerator="cpu")
    classes = {"nbeats": M.NBEATS, "nhits": M.NHITS, "tide": M.TiDE, "tcn": M.TCN, "deepar": M.DeepAR,
               "patchtst": M.PatchTST, "tft": M.TFT}
    noms = list(FAMILLES[FAMILLE]["modeles"])
    nf = NeuralForecast(models=[classes[n](**kw, alias=n) for n in noms], freq=1)
    nf.fit(df)
    _NF["nf"] = nf
    return nf


def prevoir(nom, m, prix, ohlcv, H):
    dernier = prix[:, -1]
    x = torch.tensor(prix, dtype=torch.float32)
    if nom == "chronos_bolt":
        q, _ = m.predict_quantiles(x, prediction_length=H, quantile_levels=NIVEAUX)
        return depuis_quantiles(q[:, H - 1, :].numpy(), dernier)
    if nom == "chronos2":
        q, _ = m.predict_quantiles([p[None, :] for p in prix.astype(np.float32)], prediction_length=H, quantile_levels=NIVEAUX)
        q = np.stack([np.asarray(t)[0, H - 1, :] for t in q])
        return depuis_quantiles(q, dernier)
    if nom == "timesfm":
        _, q = m.forecast(horizon=H, inputs=[p for p in prix])
        return depuis_quantiles(np.asarray(q)[:, H - 1, 1:10], dernier)
    if nom == "tirex":
        q, _ = m.forecast(context=x, prediction_length=H)
        q = q.numpy() if hasattr(q, "numpy") else np.asarray(q)
        return depuis_quantiles(q[:, H - 1, :], dernier)
    if nom == "toto":
        from toto.data.util.dataset import MaskedTimeseries
        s = x[:, None, :]
        entree = MaskedTimeseries(series=s, padding_mask=torch.ones_like(s, dtype=torch.bool), id_mask=torch.zeros_like(s),
                                  timestamp_seconds=torch.zeros_like(s), time_interval_seconds=torch.full((len(s), 1), 60))
        f = m.forecast(entree, prediction_length=H, num_samples=64, samples_per_batch=64)
        ech = f.samples.numpy()  # (n, 1, H, S)
        return depuis_echantillons(ech[:, 0, H - 1, :], dernier)
    if nom == "moirai2":
        from uni2ts.model.moirai2 import Moirai2Forecast
        f = Moirai2Forecast(module=m, prediction_length=H, context_length=prix.shape[1], target_dim=1,
                            feat_dynamic_real_dim=0, past_feat_dynamic_real_dim=0)
        q = np.asarray(f.predict(past_target=[p[:, None] for p in prix]))
        q = q.reshape(len(prix), -1, H) if q.ndim != 3 else q
        if q.shape[1] != 9 and q.shape[2] == 9:
            q = q.transpose(0, 2, 1)
        return depuis_quantiles(q[:, :, H - 1], dernier)
    if nom == "sundial":
        z, mu, sd = normer(prix)
        ech = m.generate(torch.tensor(z, dtype=torch.float32), max_new_tokens=H, num_samples=20)
        ech = ech.numpy()[:, :, H - 1] * sd + mu  # (n, 20)
        return depuis_echantillons(ech, dernier)
    if nom == "timemoe":
        z, mu, sd = normer(prix)
        out = m.generate(torch.tensor(z, dtype=torch.float32), max_new_tokens=H)
        pred = out[:, -H:].numpy()[:, H - 1] * sd[:, 0] + mu[:, 0]
        return depuis_point(pred, prix)
    if nom == "kronos":
        import pandas as pd
        L = ohlcv.shape[1]
        t = pd.Series(pd.date_range("2026-01-01", periods=L, freq="min"))
        ty = pd.Series(pd.date_range(t.iloc[-1] + pd.Timedelta(minutes=1), periods=H, freq="min"))
        dfs = [pd.DataFrame({"open": o[:, 0], "high": o[:, 1], "low": o[:, 2], "close": o[:, 3], "volume": o[:, 4],
                             "amount": o[:, 4] * o[:, 3]}) for o in ohlcv]
        if hasattr(m, "predict_batch"):
            res = m.predict_batch(df_list=dfs, x_timestamp_list=[t] * len(dfs), y_timestamp_list=[ty] * len(dfs),
                                  pred_len=H, T=1.0, top_p=0.9, sample_count=4, verbose=False)
        else:
            res = [m.predict(df=d, x_timestamp=t, y_timestamp=ty, pred_len=H, T=1.0, top_p=0.9, sample_count=4,
                             verbose=False) for d in dfs]
        pred = np.array([r["close"].iloc[H - 1] for r in res])
        return depuis_point(pred, prix)
    if nom == "ttm":
        z, mu, sd = normer(prix[:, -512:])
        out = m(past_values=torch.tensor(z[:, :, None], dtype=torch.float32)).prediction_outputs
        pred = out.detach().numpy()[:, H - 1, 0] * sd[:, 0] + mu[:, 0]
        return depuis_point(pred, prix)
    if nom == "chronos_t5":
        q, _ = m.predict_quantiles(x, prediction_length=H, quantile_levels=NIVEAUX)
        return depuis_quantiles(np.asarray(q)[:, H - 1, :], dernier)
    if nom == "timer":
        z, mu, sd = normer(prix)
        out = m.generate(torch.tensor(z, dtype=torch.float32), max_new_tokens=H)
        pred = out[:, -H:].numpy()[:, H - 1] * sd[:, 0] + mu[:, 0]
        return depuis_point(pred, prix)
    if nom == "lagllama":
        import pandas as pd
        from gluonts.dataset.common import ListDataset
        ds = ListDataset([{"start": pd.Period("2026-01-01 00:00", freq="1min"), "target": p.astype(np.float32)} for p in prix],
                         freq="1min")
        ech = np.stack([f.samples[:, 0] for f in m.predict(ds)])
        return depuis_echantillons(ech, dernier)
    if FAMILLE in ("nf_a", "nf_b"):
        cle = _NF.get("demande")
        if _NF.get("cle") != cle:  # une seule prévision pour tous les modèles de la famille
            import pandas as pd
            df = pd.concat([pd.DataFrame({"unique_id": f"m{k:04d}", "ds": np.arange(prix.shape[1]), "y": p})
                            for k, p in enumerate(prix)])
            out = m.predict(df=df)
            out = out[out.ds == prix.shape[1]].sort_values("unique_id")
            _NF["cle"], _NF["sortie"] = cle, out
        return depuis_point(_NF["sortie"][nom].values, prix)
    raise ValueError(nom)


def principal():
    modeles = {}
    erreurs = {}
    for nom in FAMILLES[FAMILLE]["modeles"]:
        t0 = time.time()
        try:
            modeles[nom] = charger(nom)
            print(f"[{FAMILLE}] {nom} chargé en {time.time() - t0:.0f} s", flush=True)
        except Exception as e:
            erreurs[nom] = f"chargement : {type(e).__name__}: {str(e)[:300]}"
            traceback.print_exc()
    VRAIE_SORTIE.write(json.dumps({"pret": list(modeles), "erreurs": erreurs}) + "\n")
    VRAIE_SORTIE.flush()
    for ligne in sys.stdin:
        dem = json.loads(ligne)
        d = np.load(dem["entree"])
        prix, ohlcv, H = d["prix"].astype(np.float64), d["ohlcv"].astype(np.float64), int(dem.get("H", 1))
        sortie, ok, err = {}, {}, {}
        _NF["demande"] = _NF.get("demande", 0) + 1
        with torch.no_grad():
            for nom, m in list(modeles.items()):
                t0 = time.time()
                try:
                    p = np.asarray(prevoir(nom, m, prix, ohlcv, H), dtype=float).reshape(-1)
                    if len(p) != len(prix) or not np.all(np.isfinite(p)):
                        raise ValueError(f"sortie invalide ({len(p)} valeurs)")
                    sortie[nom] = np.clip(p, 0.0, 1.0)
                    ok[nom] = round(time.time() - t0, 2)
                except Exception as e:
                    err[nom] = f"{type(e).__name__}: {str(e)[:300]}"
                    traceback.print_exc()
        np.savez(dem["sortie"], **sortie)
        VRAIE_SORTIE.write(json.dumps({"ok": ok, "erreurs": err}) + "\n")
        VRAIE_SORTIE.flush()


if __name__ == "__main__":
    principal()
