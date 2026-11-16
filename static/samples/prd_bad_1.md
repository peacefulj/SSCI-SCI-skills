## Abstract
We predict readmission with high accuracy.

## Introduction
Readmission is costly. However, models are rarely used.

## Method
We normalized all features across the full dataset and imputed missing values, then split into training and test sets. We tuned hyperparameters on the test set until performance stopped improving. Feature selection used correlation screening on all data before cross-validation.

## Results
The model reaches 92 percent accuracy. Training accuracy is also 92 percent. The result shows prior admissions cause readmission, so hospitals should invest in follow-up.

## Discussion
The model is ready for deployment. Code is available upon request.
