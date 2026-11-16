## Abstract
We develop a model predicting 30-day readmission from electronic health records, achieving an AUC of 0.81 on a held-out test set.

## Introduction
Readmission prediction could target scarce resources. However, existing models are rarely evaluated on held-out data. We address this gap.

## Method
We used a 70/15/15 train-validation-test split, stratified by outcome, with the test set touched once after model selection. All preprocessing, including standardization and imputation, was fitted on the training set only and applied unchanged to held-out data. Folds were grouped by patient to prevent leakage from repeated admissions.

Hyperparameters were tuned by 10-fold cross-validation repeated 5 times using grid search over learning rate, depth and regularization; the selected values are reported in Table 2. Feature selection was performed inside each fold via recursive elimination.

We report precision, recall, F1 and AUC. A trivial baseline predicting the majority class is included for reference, and a gradient-boosted model over raw features serves as a naive baseline. Calibration was assessed with a reliability diagram and Brier score.

## Results
On the test set the model reaches AUC 0.81 (95% CI 0.78 to 0.84), precision 0.42 and recall 0.55, versus AUC 0.63 for the naive baseline. The training-to-validation gap in log loss is 0.04, indicating no material overfitting. We report prediction intervals for individual risk using conformal methods, and uncertainty is propagated to the decision threshold.

## Discussion
Feature importance is reported by permutation importance; we interpret it as predictive, not causal. One limitation is the single-centre setting. Code, random seeds and the analysis environment are available at the repository link.
