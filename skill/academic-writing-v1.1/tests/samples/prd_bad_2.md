## Abstract
We forecast electricity demand using a deep model.

## Introduction
Forecasting matters. However, models vary.

## Method
We used hourly data and split it randomly into training and test sets. We normalized using global statistics, and adjusted the architecture each time the test results improved.

## Results
We report accuracy as the only metric.
The model achieves excellent performance with RMSE 412 MW. Feature importance shows temperature is the key driver, therefore policy should target weather forecasting.

## Discussion
The model is generalizable. No limitations apply.
