## Abstract
We build a defect classifier for a manufacturing line, reaching 0.74 recall at 0.61 precision on held-out batches.

## Introduction
Manual inspection is costly and inconsistent. However, reported classifiers are often evaluated on the same batches used for tuning. We use a leakage-safe protocol.

## Method
We split data into training, validation and test sets at the batch level, so that images from one batch never appear in two sets. Preprocessing, including normalization and missing-value imputation, was fitted on the training set only.

Model selection used 10-fold cross-validation with folds grouped by batch, repeated 5 times. Hyperparameters were tuned by random search over a documented range. Feature selection was applied inside each training fold.

Because defects are rare (2.1 percent), we report precision, recall and F1 rather than accuracy alone, and we correct class imbalance through class weighting. We include a majority-class baseline and a naive baseline using raw pixel means.

## Results
The test set yields recall 0.74, precision 0.61 and AUC 0.84, against 0.11 recall for the majority-class baseline. The training-test gap in F1 is 0.03. Prediction uncertainty is reported per batch using conformal prediction sets.

## Discussion
Permutation importance ranks texture contrast highest; this is a predictive statement only. A limitation is that only one product family was sampled. Code, seeds and environment files are released.
