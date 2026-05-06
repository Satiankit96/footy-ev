"""Models: pre-match probability estimators."""

from footy_ev.models.dixon_coles import DCFit, fit, log_likelihood, predict_1x2
from footy_ev.models.xg_skellam import (
    InsufficientTrainingData,
    XGSkellamFit,
    predict_ou25,
)
from footy_ev.models.xg_skellam import (
    fit as xg_fit,
)
from footy_ev.models.xgboost_ou25 import (
    XGBoostOU25Fit,
)
from footy_ev.models.xgboost_ou25 import (
    fit as xgb_fit,
)
from footy_ev.models.xgboost_ou25 import (
    predict_ou25 as xgb_predict_ou25,
)

__all__ = [
    "DCFit",
    "fit",
    "log_likelihood",
    "predict_1x2",
    "InsufficientTrainingData",
    "XGSkellamFit",
    "xg_fit",
    "predict_ou25",
    "XGBoostOU25Fit",
    "xgb_fit",
    "xgb_predict_ou25",
]
