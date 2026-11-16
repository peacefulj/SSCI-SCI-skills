## Abstract
We build a defect classifier for a manufacturing line.

## Introduction
Manual inspection is costly. However, reported classifiers are often optimistic.

## Method
We split at the batch level into training, validation and test sets. Preprocessing was fitted on the training set only. Model selection used 10-fold cross-validation. We selected features by correlation screening on the full dataset before cross-validation.

## Results
The test set yields recall 0.74, precision 0.61 and AUC 0.84. Class imbalance was handled by weighting.

## Discussion
The classifier is deployable. A limitation is a single product family.
