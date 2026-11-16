## Abstract
We forecast electricity demand using gradient boosting.

## Introduction
Forecasting reduces costs. However, many models report in-sample fit.

## Method
We use hourly data from 2018 to 2023 and split into training, validation and test periods. We tuned hyperparameters by grid search. We report RMSE and R2.

## Results
Test RMSE is 412 MW. The model performs well across horizons. Feature importance ranks temperature first, so the operator should invest in weather data.

## Discussion
The model reduces costs. A limitation is the single region.
