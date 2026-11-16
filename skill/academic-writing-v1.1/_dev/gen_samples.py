# -*- coding: utf-8 -*-
"""生成验收样稿。好档满足全部检测器；中/坏档按规则植入缺陷。"""
import os

OUT = r'C:\Users\appro\WorkBuddy\2026-11-11-06-47-14\academic-writing-v1.1\tests\samples'
os.makedirs(OUT, exist_ok=True)

S = {}

# ==================== QUANT ====================
S['qnt_good_1.md'] = """## Abstract
We estimate the causal effect of provincial innovation subsidies on firm R&D intensity. Using a difference-in-differences design on 8,412 listed firms, we find subsidies raise R&D intensity by 0.9 percentage points.

## Introduction
Whether industrial policy raises private R&D remains contested. However, existing work relies mostly on cross-province comparisons, which are confounded by local economic conditions. We make three contributions to this literature.

## Data and Method
Our identification strategy exploits the 2015 pilot program, which granted subsidies to firms in selected provinces. The key assumption is plausible because pilot selection followed a pre-announced scoring rule based on pre-2014 outcomes only. We estimate a difference-in-differences model with firm and year fixed effects.

The identifying assumption of parallel trends is supported by an event study: pre-treatment coefficients are jointly insignificant (p = 0.62). Standard errors are clustered at the province level, where treatment is assigned.

## Results
Subsidies raise R&D intensity by 0.9 percentage points (95% CI 0.4 to 1.4), or 0.21 of a standard deviation, equivalent to 14 percent of the sample mean.

## Discussion
The estimate is local to the pilot provinces. One limitation is that we cannot observe informal R&D spending.
"""

S['qnt_good_2.md'] = """## Abstract
We study whether access to bank credit raises small-firm employment. Using a policy that expanded branch licensing, we instrument credit access and estimate a local average treatment effect of 3.2 employees per firm.

## Introduction
Credit constraints are widely believed to suppress hiring, but credible evidence is scarce. However, prior estimates confound credit supply with local demand. This paper provides new evidence.

## Identification
Our identification strategy exploits the 2011 county-level branch licensing reform. The exclusion restriction is that licensing affects employment only through credit access; we test this by showing no effect on placebo outcomes that credit cannot affect. That assumption is plausible because licensing was assigned by a national quota unrelated to county employment trends.

The first stage is strong: the reform raises credit access by 18 percentage points, with an F-statistic of 34.2. Because the estimand is a LATE for compliers, we do not extrapolate to firms whose credit access did not respond.

## Results
The 2SLS estimate is 3.2 employees (95% CI 1.1 to 5.3), or 0.18 of a standard deviation.

## Discussion
A limitation is that compliers are disproportionately young firms.
"""

S['qnt_good_3.md'] = """## Abstract
We examine whether board gender quotas affect firm risk. Using propensity score matching on pre-reform covariates, we find a modest reduction in earnings volatility.

## Introduction
Quotas are controversial, yet causal evidence is thin. However, existing studies compare adopting and non-adopting firms without adjusting for selection. This paper addresses that gap.

## Method
Our identification strategy relies on unconfoundedness conditional on pre-reform covariates. This assumption is plausible because the quota applied to firms above a size threshold set years earlier, and we match on that threshold's determinants.

The propensity score is estimated by logit on twelve pre-treatment covariates. We report overlap and common support diagnostics, and trim observations outside the common support. Balance is assessed with standardized mean differences, all below 0.1 after matching.

Standard errors are bootstrapped with 500 replications. As a sensitivity analysis, we report Rosenbaum bounds: an unobserved confounder would need to raise the odds of treatment by 1.8 times to overturn the result.

## Results
The matched estimate is a 0.6 percentage point reduction in volatility (95% CI -1.1 to -0.1), or 0.11 of a standard deviation.

## Discussion
One limitation is that we cannot rule out anticipation effects.
"""

S['qnt_mid_1.md'] = """## Abstract
We study the effect of innovation subsidies on R&D. Using difference-in-differences on listed firms, we find a positive effect.

## Introduction
Industrial policy is widely debated. However, evidence on Chinese subsidies remains limited, and this paper fills that gap.

## Method
We estimate a difference-in-differences model with firm and year fixed effects. The parallel trends assumption holds in our event study. We also examine heterogeneity across ownership types and find that the effect is concentrated in state-owned firms.

## Results
The coefficient on subsidy is 0.009 and is significant at the 1% level. Table 2 reports the heterogeneity results.

## Discussion
The findings suggest subsidies are effective. One limitation is data coverage.
"""

S['qnt_mid_2.md'] = """## Abstract
This paper estimates the effect of credit access on employment using an instrument based on branch licensing.

## Introduction
Credit constraints may suppress hiring. However, credible estimates are scarce.

## Identification
Our identification strategy exploits county-level licensing reform. The first stage shows that the reform raises credit access substantially.

## Results
The 2SLS coefficient is 3.2 and is significant. We also run subgroup analyses by firm age and by region, reporting several significant differences.

## Discussion
The results are consistent with credit constraints binding. A limitation is sample attrition.
"""

S['qnt_mid_3.md'] = """## Abstract
We examine whether board quotas affect firm risk using propensity score matching.

## Introduction
Quotas remain controversial. However, causal evidence is limited.

## Method
Our identification strategy relies on unconfoundedness conditional on pre-reform covariates, which is plausible because the threshold was set years earlier. We match treated and control firms on twelve covariates and report overlap diagnostics.

## Results
The matched estimate is a 0.6 percentage point reduction in volatility, significant at the 5% level.

## Discussion
The results support the risk-reduction view. One limitation is the short post period.
"""

S['qnt_bad_1.md'] = """## Abstract
We show that innovation subsidies cause higher firm performance. Using cross-sectional data on 3,000 firms, we find strong effects.

## Introduction
Subsidies matter. However, prior work is limited.

## Method
We run OLS with a rich set of control variables, which addresses endogeneity. We also use an instrumental variable and a propensity score matching approach as robustness checks. We examine heterogeneity across many subgroups and report the significant ones.

## Results
The coefficient on subsidy is positive and significant at the 1% level. This proves that subsidies cause higher ROA. Table 1 shows the results.

## Discussion
Subsidies should be expanded. Future work can explore mechanisms.
"""

S['qnt_bad_2.md'] = """## Abstract
We estimate the effect of credit access on employment.

## Introduction
Credit constraints suppress hiring. However, evidence is scarce.

## Method
We use an instrumental variable strategy based on branch licensing. We also control for a rich set of covariates, which solves the endogeneity problem.

## Results
The 2SLS coefficient is 3.2 and is significant at the 5% level. Since the instrument is valid, this is the causal effect for the population.

## Discussion
The result implies credit constraints bind. There are no major limitations.
"""

S['qnt_bad_3.md'] = """## Abstract
We study board quotas and firm risk using propensity score matching.

## Introduction
Quotas are controversial. However, causal evidence is limited.

## Method
We use propensity score matching to construct a control group. We estimate the propensity score by logit.

## Results
The matched estimate is -0.6 percentage points and is significant at the 5% level. Since matching removes selection bias, the estimate is causal.

## Discussion
Quotas reduce risk. This finding is generalizable to all firms.
"""

# ==================== QUALITATIVE ====================
S['qlt_good_1.md'] = """## Abstract
This study examines how middle managers interpret the introduction of algorithmic performance systems. Using an instrumental case study design, we identify three interpretive repertoires.

## Introduction
Algorithmic management is spreading, yet we know little about how managers make sense of it. However, existing accounts treat managers as passive recipients. This paper asks how they interpret the system.

## Method
We adopt a case study design bounded by the digital unit of a retail bank and the period 2019-2022. Participants were recruited through purposive maximum variation sampling across tenure and function; recruitment continued until saturation, defined as four consecutive interviews producing no new codes.

We used first-cycle descriptive coding followed by pattern coding, supported by a codebook listing 14 codes with definitions and exemplars. Analytic memos were written after each interview. Two coders independently coded 20 percent of transcripts, reaching a kappa of 0.81. Data comprise 24 interviews averaging 62 minutes, 610 pages of transcript, and 140 hours of observation.

Findings are displayed in a theme-by-case matrix. We document a chain of evidence linking excerpts to codes to themes, and we assessed rival explanations, including workload pressure as an alternative driver. Credibility was supported by triangulation across interviews, observation and internal documents. The first author's prior employment at the bank is acknowledged as a source of reflexivity risk. Ethics approval was granted by the university committee, and informed consent was obtained.

## Results
Managers framed the system as an "impartial mirror that removes favouritism from appraisals" (P03, interview). Yet a minority resisted, describing it as "a black box that scores us on things we cannot see" (P11). This tension constitutes our first theme, and we treat P11 as a negative case that bounds the claim.
"""

S['qlt_good_2.md'] = """## Abstract
We explore how nurses experience the shift to remote triage. Using interpretive phenomenological analysis, we identify four superordinate themes.

## Introduction
Remote triage reshaped clinical work. However, little is known about how nurses make sense of the change. This study asks how they experience it.

## Method
We adopt interpretive phenomenological analysis with a homogeneous purposive sample of ten nurses, all with at least two years of telephone triage experience. Sampling was purposive to preserve homogeneity of experience. Data collection continued to saturation, defined as no new themes in the final three interviews.

Analysis followed first-cycle descriptive coding and second-cycle pattern coding, with a codebook recording definitions. Two coders reached a kappa of 0.79. Analytic memos documented emerging interpretations. The corpus comprises 10 interviews, 240 pages of transcript.

Credibility was enhanced through triangulation of interviews and reflective diaries, and member checking of summaries. A theme-by-case matrix displays convergence. We discuss rival explanations, including staffing levels. The researchers' clinical background is stated as a reflexivity consideration. Ethics approval was obtained from the NHS committee and informed consent was recorded.

## Results
Participants described the screen as "a wall that lets me hide when I am not sure" (P04, interview), while another described it as "the only place I feel I can think" (P07). One participant dissented, reporting no change, and we retain this contrary case.
"""

S['qlt_good_3.md'] = """## Abstract
This ethnography examines how a manufacturing plant absorbed a safety program. We show how ritual compliance coexisted with genuine learning.

## Introduction
Safety programs often fail quietly. However, accounts of failure rarely explain how compliance and learning coexist. This paper asks how workers enact safety rules.

## Method
We conducted a twelve-month ethnography with purposive sampling of three shifts. Immersion allowed observation of routine and exceptional practice. Data comprise 320 hours of observation, 41 interviews averaging 55 minutes, and 900 pages of field notes. Collection continued to saturation, judged by the absence of new codes across two months.

Coding proceeded through first-cycle descriptive coding and second-cycle pattern coding, using a codebook with 22 codes. Analytic memos tracked interpretive shifts. Two coders reached a kappa of 0.83.

Trustworthiness rests on triangulation of observation, interviews and documents, an audit trail of coding decisions, and member checking with shift supervisors. A matrix maps themes against shifts. We consider rival explanations, notably that observed compliance reflected managerial surveillance rather than learning. The first author's position as a former safety officer is discussed as reflexivity. Ethics approval and informed consent were obtained.

## Results
Workers described drills as "a performance for the cameras" (P08, observation note), while also describing genuine learning after an incident. One shift showed no learning, a negative case we analyse separately.
"""

S['qlt_mid_1.md'] = """## Abstract
This study examines how managers interpret algorithmic performance systems.

## Introduction
Algorithmic management is spreading. However, we know little about managerial interpretation.

## Method
We conducted 24 semi-structured interviews in a retail bank. Data were coded thematically. We used purposive sampling across functions.

## Results
Managers described the system as "an impartial mirror that removes favouritism from appraisals". Others described it as "a black box that scores us on things we cannot see". A third group described it as "a tool we have learned to game". These three repertoires organize our findings.

## Discussion
The study contributes to the literature on algorithmic management. A limitation is the single case.
"""

S['qlt_mid_2.md'] = """## Abstract
We explore nurses' experience of remote triage using interpretive phenomenological analysis.

## Introduction
Remote triage reshaped clinical work. However, nurses' experience is understudied.

## Method
We interviewed ten nurses. Sampling was purposive and homogeneous. Analysis followed first-cycle descriptive coding and second-cycle pattern coding. We kept a codebook.

## Results
Nurses described the screen as "a wall that lets me hide when I am not sure". Several described it as "the only place I feel I can think". We present four themes.

## Discussion
The findings extend work on remote care. A limitation is the small sample.
"""

S['qlt_mid_3.md'] = """## Abstract
This ethnography examines a safety program in a manufacturing plant.

## Introduction
Safety programs often fail quietly. However, explanations of coexistence are rare.

## Method
We observed three shifts for twelve months and conducted interviews. Data comprise 320 hours of observation and 41 interviews. Coding used first-cycle and second-cycle methods with a codebook.

## Results
Workers described drills as "a performance for the cameras". They also described learning after an incident. We organize findings into three themes.

## Discussion
The study shows compliance and learning coexist. A limitation is generalizability.
"""

S['qlt_bad_1.md'] = """## Abstract
This paper studies algorithmic management in a bank.

## Introduction
Algorithmic management is important. However, research is limited.

## Method
We did 24 interviews and analysed them.

## Results
Managers said "an impartial mirror that removes favouritism from appraisals". Another said "a black box that scores us on things we cannot see". A third said "a tool we have learned to game". A fourth said "it is just a spreadsheet with a nice interface". A fifth said "we ignore it when it suits us". These quotes show the range of views.

## Discussion
The findings are generalizable. Future research should explore other sectors.
"""

S['qlt_bad_2.md'] = """## Abstract
We study nurses and remote triage.

## Introduction
Telehealth is growing. However, evidence is limited.

## Method
We interviewed nurses about their experience and used thematic analysis.

## Results
Nurses felt the screen was "a wall that lets me hide when I am not sure". Another felt it was "the only place I feel I can think". Another said "it is exhausting but clarifying". Another said "patients treat us differently now". We identified themes of hiding, thinking, exhaustion, and patient relations.

## Discussion
Remote triage changes nursing. The findings can be generalized to all clinical settings.
"""

S['qlt_bad_3.md'] = """## Abstract
This paper examines a safety program.

## Introduction
Safety matters. However, research is limited.

## Method
We did an ethnography.

## Results
Workers said "a performance for the cameras". Another said "the drills are theatre". Another said "we do it because we must". Another said "real learning happens after incidents". These quotes illustrate the culture.

## Discussion
The study shows safety culture is complex. There are no limitations.
"""

# ==================== PREDICTIVE ====================
S['prd_good_1.md'] = """## Abstract
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
"""

S['prd_good_2.md'] = """## Abstract
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
"""

S['prd_good_3.md'] = """## Abstract
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
"""

S['prd_mid_1.md'] = """## Abstract
We predict 30-day readmission and reach an AUC of 0.81.

## Introduction
Readmission prediction is useful. However, models are rarely validated.

## Method
We split the data into training and test sets. We standardized features and imputed missing values. Hyperparameters were tuned by 10-fold cross-validation. We report accuracy as the main metric.

## Results
The model reaches 0.81 AUC on the test set. Training accuracy is 0.88. Feature importance ranks prior admissions first.

## Discussion
The model is useful for triage. A limitation is the single centre.
"""

S['prd_mid_2.md'] = """## Abstract
We forecast electricity demand using gradient boosting.

## Introduction
Forecasting reduces costs. However, many models report in-sample fit.

## Method
We use hourly data from 2018 to 2023 and split into training, validation and test periods. We tuned hyperparameters by grid search. We report RMSE and R2.

## Results
Test RMSE is 412 MW. The model performs well across horizons. Feature importance ranks temperature first, so the operator should invest in weather data.

## Discussion
The model reduces costs. A limitation is the single region.
"""

S['prd_mid_3.md'] = """## Abstract
We build a defect classifier for a manufacturing line.

## Introduction
Manual inspection is costly. However, reported classifiers are often optimistic.

## Method
We split at the batch level into training, validation and test sets. Preprocessing was fitted on the training set only. Model selection used 10-fold cross-validation. We selected features by correlation screening on the full dataset before cross-validation.

## Results
The test set yields recall 0.74, precision 0.61 and AUC 0.84. Class imbalance was handled by weighting.

## Discussion
The classifier is deployable. A limitation is a single product family.
"""

S['prd_bad_1.md'] = """## Abstract
We predict readmission with high accuracy.

## Introduction
Readmission is costly. However, models are rarely used.

## Method
We normalized all features across the full dataset and imputed missing values, then split into training and test sets. We tuned hyperparameters on the test set until performance stopped improving. Feature selection used correlation screening on all data before cross-validation.

## Results
The model reaches 92 percent accuracy. Training accuracy is also 92 percent. The result shows prior admissions cause readmission, so hospitals should invest in follow-up.

## Discussion
The model is ready for deployment. Code is available upon request.
"""

S['prd_bad_2.md'] = """## Abstract
We forecast electricity demand using a deep model.

## Introduction
Forecasting matters. However, models vary.

## Method
We used hourly data and split it randomly into training and test sets. We normalized using global statistics.

## Results
The model achieves excellent performance with RMSE 412 MW. Feature importance shows temperature is the key driver, therefore policy should target weather forecasting.

## Discussion
The model is generalizable. No limitations apply.
"""

S['prd_bad_3.md'] = """## Abstract
We build a defect detector.

## Introduction
Inspection is manual. However, automation is promising.

## Method
We trained a classifier and evaluated with cross-validation.

## Results
Accuracy is 97 percent. The model outperforms baselines.

## Discussion
The detector works. Code available on request.
"""

# ==================== CLINICAL ====================
S['cln_good_1.md'] = """## Title
Nurse-led remote monitoring for hypertension control: a randomized controlled trial

## Abstract
We assessed whether nurse-led remote monitoring improves blood pressure control. This study is reported in accordance with CONSORT 2025.

## Introduction
Hypertension control remains suboptimal. However, evidence on nurse-led remote monitoring is limited in primary care.

## Methods
Adults with uncontrolled hypertension were randomized to remote monitoring or usual care. Randomization used a computer-generated sequence with permuted blocks of four, prepared by an independent statistician. Allocation was concealed through a central web-based system. Participants and outcome assessors were blinded to allocation, while care providers were not, because the intervention required their involvement.

The primary outcome was change in systolic pressure at 12 months; secondary outcomes were prespecified in the protocol. Assuming a 7 mmHg difference, alpha 0.05 and 80 percent power, 210 participants per arm were required. Ethics approval was obtained from the regional ethics committee (No. 2021-118), and written informed consent was recorded. The trial was registered (NCT04812345) before the first participant was enrolled.

## Results
Participant flow is shown in the flow diagram (Figure 1). Baseline characteristics were balanced (Table 1). Systolic pressure fell 9.1 mmHg with remote monitoring versus 4.2 mmHg with usual care, a difference of 4.9 mmHg (95% CI 2.7 to 7.1). Absolute risk difference for controlled hypertension was 14 percentage points (95% CI 5 to 23), with an NNT of 7. Adverse events were reported in Table 3; no serious events were attributed to the intervention. Subgroup analyses were prespecified and exploratory analyses are labelled as such.

## Discussion
The effect is consistent with prior trials but smaller than in specialist settings. Limitations include the single-region setting and the open-label design for providers. De-identified data are available from the corresponding author upon reasonable request and ethics approval.
"""

S['cln_good_2.md'] = """## Title
Preoperative biomarkers and postoperative delirium: a prospective cohort study

## Abstract
We examined whether preoperative inflammatory markers predict postoperative delirium. This study is reported in accordance with STROBE.

## Introduction
Delirium complicates recovery. However, whether routine biomarkers add predictive value is unclear.

## Methods
We enrolled consecutive adults undergoing elective surgery between 2019 and 2022. Inclusion required age over 65 and expected stay beyond 24 hours; patients with preoperative cognitive impairment were excluded. Sample size was determined by the number of eligible admissions during the study window, and we report a post hoc power calculation.

Delirium was assessed daily with the CAM. Confounders were selected a priori using a directed acyclic graph and included age, ASA class, baseline cognition and surgical duration. Missing biomarker values (6.2 percent) were handled by multiple imputation, with complete-case results reported as a sensitivity analysis.

Ethics approval was obtained from the institutional review board (No. 2019-233), and informed consent was obtained from all participants or their proxies. Statistical analyses used 95 percent confidence intervals throughout.

## Results
Of 1,842 patients, 214 developed delirium. Baseline characteristics are shown in Table 1. Each doubling of CRP was associated with an odds ratio of 1.34 (95% CI 1.12 to 1.60), corresponding to an absolute risk difference of 6 percentage points (95% CI 2 to 10) and an NNT of 17.

## Discussion
Residual confounding by frailty is plausible and would likely inflate the association. Results may not transfer to settings without routine CAM assessment. Data are available from the corresponding author under a data use agreement.
"""

S['cln_good_3.md'] = """## Title
Vascular access strategies and dialysis outcomes: a systematic review and meta-analysis

## Abstract
We synthesized trials comparing fistula-first and catheter-first strategies. This review is reported in accordance with PRISMA 2020.

## Introduction
Access strategy affects dialysis outcomes. However, trials are small and conclusions inconsistent.

## Methods
We searched PubMed, Embase and the Cochrane Library from inception to March 2024 using a search strategy reported in Appendix 1, combining MeSH terms and free text with no language restriction. Two reviewers screened records independently.

Risk of bias was assessed with RoB 2 for randomized trials and ROBINS-I for non-randomized studies; disagreements were resolved by a third reviewer. Effect estimates were pooled with random-effects models. Certainty of evidence was graded with GRADE, with reasons for downgrading reported. The protocol was registered in PROSPERO (CRD42023456789).

## Results
The flow diagram (Figure 1) summarizes identification, screening and inclusion. Of 2,410 records, 18 studies met criteria. Fistula-first strategy reduced infection risk (risk ratio 0.62, 95% CI 0.48 to 0.80; absolute risk difference -7 percentage points, 95% CI -11 to -3; NNT 14; I2 = 31 percent). GRADE certainty was moderate, downgraded for imprecision.

## Discussion
The evidence is limited by few trials in older populations. Data availability statements for included studies are listed in Appendix 2.
"""

S['cln_mid_1.md'] = """## Title
Nurse-led remote monitoring for hypertension: a randomized trial

## Abstract
We assessed whether remote monitoring improves blood pressure control.

## Introduction
Hypertension control is suboptimal. However, evidence is limited.

## Methods
Patients were randomized to remote monitoring or usual care. Randomization was computer-generated. The primary outcome was change in systolic pressure at 12 months. A total of 210 per arm were enrolled.

## Results
Systolic pressure fell 9.1 mmHg with remote monitoring versus 4.2 mmHg with usual care, a difference of 4.9 mmHg (95% CI 2.7 to 7.1). Baseline characteristics are shown in Table 1. Adverse events were uncommon.

## Discussion
The intervention is effective. A limitation is the single-region setting.
"""

S['cln_mid_2.md'] = """## Title
Preoperative biomarkers and postoperative delirium: a cohort study

## Abstract
We examined whether inflammatory markers predict delirium.

## Introduction
Delirium complicates recovery. However, biomarker evidence is unclear.

## Methods
We enrolled consecutive adults aged over 65 undergoing elective surgery. Delirium was assessed with the CAM. Confounders included age, ASA class and surgical duration. Missing values were handled by complete-case analysis. Ethics approval was obtained.

## Results
Of 1,842 patients, 214 developed delirium. Each doubling of CRP was associated with an odds ratio of 1.34 (95% CI 1.12 to 1.60). Baseline data are in Table 1.

## Discussion
The association is plausibly causal. A limitation is residual confounding.
"""

S['cln_mid_3.md'] = """## Title
Access strategies and dialysis outcomes: a systematic review

## Abstract
We synthesized trials comparing access strategies.

## Introduction
Access strategy affects outcomes. However, trials are small.

## Methods
We searched PubMed and Embase. Two reviewers screened records. Risk of bias was assessed. Effects were pooled with random-effects models.

## Results
Of 2,410 records, 18 studies were included. Fistula-first reduced infection (risk ratio 0.62, 95% CI 0.48 to 0.80). Heterogeneity was moderate.

## Discussion
The evidence supports fistula-first. A limitation is few trials in older patients.
"""

S['cln_bad_1.md'] = """## Title
Remote monitoring improves hypertension control

## Abstract
We studied remote monitoring for hypertension.

## Introduction
Hypertension is common. However, evidence is limited.

## Methods
Patients were allocated to remote monitoring or usual care. We assessed blood pressure at 12 months. Sample size was chosen as 210 per arm.

## Results
Blood pressure fell more in the intervention group, and the difference was significant (p < 0.05). Adverse events were not reported in detail.

## Discussion
Remote monitoring works and should be adopted widely. No major limitations.
"""

S['cln_bad_2.md'] = """## Title
Inflammatory markers predict delirium

## Abstract
We studied biomarkers and delirium.

## Introduction
Delirium is common. However, evidence is limited.

## Methods
We enrolled older surgical patients and measured CRP. Delirium was diagnosed clinically. We adjusted for several confounders.

## Results
Higher CRP was associated with delirium. The association was significant. This proves inflammation causes delirium.

## Discussion
The finding is generalizable to all surgical patients. No limitations.
"""

S['cln_bad_3.md'] = """## Title
Access strategy and dialysis outcomes

## Abstract
We reviewed the literature on access strategies.

## Introduction
Access matters. However, studies vary.

## Methods
We searched several databases and selected relevant studies. We pooled the results.

## Results
Fistula-first was better. The pooled estimate favoured fistula-first.

## Discussion
Fistula-first should be adopted. No limitations apply.
"""

# ==================== BASIC SCIENCE ====================
S['sci_good_1.md'] = """## Abstract
We report the thermal conductivity of graphene oxide films below 50 nm, measured at 4.2 W m-1 K-1 for 20 nm films.

## Introduction
Graphene oxide films are promising for thermal management. However, thickness-dependent conductivity below 50 nm is poorly characterized. Here we measure films from 10 to 50 nm.

## Materials and Methods
Graphene oxide (≥99% purity, Xianfeng Nanotech, Nanjing, China) was dispersed in deionized water. Films were spin-coated at 2000 rpm for 60 s, then annealed at 400 °C for 2 h under Ar flow (50 sccm).

Thickness was measured by atomic force microscopy (Bruker Dimension Icon). Thermal conductivity was obtained with a 3-omega setup (custom, model TCM-1) at room temperature. Measurements were repeated five times per sample; values are reported as mean ± SD. Statistical comparison used one-way ANOVA with Tukey HSD (α = 0.05) in OriginPro 2023.

## Results
Conductivity decreased from 6.8 ± 0.3 to 4.2 ± 0.2 W m-1 K-1 as thickness fell from 50 to 20 nm (n = 5, p < 0.01). Values below 20 nm were not measurable because films delaminated.

## Discussion
The thickness dependence is consistent with boundary scattering. One limitation is that films thinner than 20 nm could not be measured, so the extrapolation to monolayer is not supported. Animal experiments were not involved. We did not rely on secondary citations.
"""

S['sci_mid_1.md'] = """## Abstract
We measure thermal conductivity of graphene oxide films.

## Introduction
Graphene oxide is promising. However, thin films are poorly characterized.

## Materials and Methods
Graphene oxide was purchased commercially and dispersed in water. Films were spin-coated and annealed. Thickness was measured by AFM. Thermal conductivity was measured at room temperature.

## Results
Conductivity decreased with thickness, from 6.8 to 4.2 W m-1 K-1.

## Discussion
The trend is consistent with boundary scattering. A limitation is that thinner films delaminated.
"""

S['sci_bad_1.md'] = """## Abstract
We study graphene oxide films.

## Introduction
Graphene oxide is important. However, studies are limited.

## Materials and Methods
Graphene oxide was obtained commercially. Films were made and annealed. Conductivity was measured.

## Results
Conductivity was 4.2 W m-1 K-1 and decreased with thickness. The values were as expected.

## Discussion
The results are important. No limitations.
"""

for name, text in S.items():
    with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
        f.write(text)

print('写入', len(S), '个样稿')
