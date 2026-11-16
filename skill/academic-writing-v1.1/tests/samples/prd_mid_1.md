## Abstract
We predict 30-day readmission and reach an AUC of 0.81.

## Introduction
Readmission prediction is useful. However, models are rarely validated.

## Method
We split the data into training and test sets. We standardized features and imputed missing values. Hyperparameters were tuned by 10-fold cross-validation. We report accuracy as the main metric.

## Results
The model reaches 0.81 AUC on the test set. Training accuracy is 0.88. Feature importance ranks prior admissions first.

## Discussion
The model is useful for triage. A limitation is the single centre.
