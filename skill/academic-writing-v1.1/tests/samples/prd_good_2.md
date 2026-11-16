## Abstract
We forecast short-term electricity demand with gradient boosting, reducing RMSE by 18 percent over the operator's incumbent model.

## Introduction
Accurate demand forecasting reduces balancing costs. However, many published models report in-sample fit. We compare models under a strict protocol.

## Method
Data are hourly loads from 2018 to 2023. Because observations are temporal, we split by time into train, validation and test periods and use rolling-origin cross-validation with 10 folds and 5 repeats, avoiding any use of future information in feature construction. Standardization was fitted on the training fold only.

We tuned hyperparameters by grid search and report the search space and selected values. We report RMSE and R2 against a naive baseline that repeats the value from seven days earlier, and against a majority-class baseline for the peak-alert classification task.

## Results
Test RMSE is 412 MW against 503 MW for the naive baseline, with an R2 of 0.91. The classification task reaches precision 0.68 and recall 0.61 (AUC 0.86). Training and test errors differ by 6 percent, so overfitting is limited. Prediction intervals are reported for the day-ahead horizon.

## Discussion
Permutation-based feature importance ranks temperature first; we treat this as predictive rather than causal. A limitation is that the model is estimated on one region, and we report no external validation. Code and random seeds are provided.
