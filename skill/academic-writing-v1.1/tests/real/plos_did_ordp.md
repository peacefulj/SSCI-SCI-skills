# Effect of place-based policy on regional economic growth: A quasi-natural experiment from China's Old Revolutionary Development Program

Source: Pan D, Zhou P, Kong F (2023). PLoS ONE 18(7): e0288901. https://doi.org/10.1371/journal.pone.0288901
License: CC BY 4.0. Verbatim excerpts of Abstract / Introduction / Data and method / Empirical results / Conclusions.

## Abstract
Triggering economic growth is a requirement to promote human welfare and realize sustainable development in many developing countries. However, place-based policies' impact on economic growth is debatable, and its underlying mechanism is unknown. China's Old Revolutionary Development Program (ORDP) is a large-scale and novel type of place-based policy targeted at undeveloped regions in China. We evaluate the effect of ORDP on economic growth by employing a time-varying difference-in-differences model and further explore the potential mechanisms and heterogeneity effects. VIIRS/DNB nightlight data is used to measure economic growth. We find that ORDP can significantly promote economic growth by 4.0% and the result is still robust after several tests. Mechanism analysis shows that ORDP can improve economic growth through government intervention, industrial structure optimization, and information infrastructure construction. Heterogeneity analysis indicates that the ORDP performs better on economic growth in central Chinese cities and high-economy cities.

## Introduction
Place-based policies are spatially targeted and intended to promote economic growth in specific areas [5, 6]. Theoretically, place-based policies can stimulate economic growth in less developed areas and reduce regional disparity [7, 8]. However, in empirical studies, no consensus has been reached about place-based policies' effect on the economy. Some studies prove that place-based policies help boost economic development [5, 9-11]. While another strand of literature holds the opposite view [4, 12-14]. Hence, whether place-based policies can promote economic growth or not has not been confirmed and the underlying mechanisms of these two contradictory effects deserve attention. Therefore, we present the following research questions: Can place-based policies drive economic growth in targeted regions? Does this impact have heterogeneity in different regions? And what are the mechanisms behind it?

To address the questions raised above, we make use of China's Old Revolutionary Development Program policy (ORDP) as a form of place-based policy. It was implemented gradually, starting with 15 prefecture-level cities in 2012, followed by 10 cities in 2015 and 8 cities in 2016. Due to the limited availability of nightlight data which begins in 2013, we selected 18 prefecture-level cities that adopted ORDP in 2015 and 2016 as the experimental group. The control group consisted of 60 non-ORDP cities in the same provinces as the experimental group. Then, the Parallel Trend Assumption (PTA), which requires the control and experimental groups to share comparable economic development trends before the implementation of ORDP, was satisfied by doing this. We find that ORDP can increase economic growth by 4.0%.

Our paper makes the following four possible contributions. First, we supplement the burgeoning debate about whether place-based policies can improve economic growth. Second, we examine how China is affected by place-based policies. Third, we use VIIRS/DNB nightlight value to measure economic development, which can more accurately reflect real economic growth in China. Fourth, the DID method is utilized to rigorously test the relationship between ORDP and economic performance. Simple OLS estimation may bias the evaluation of policy effects [27], while DID method can reduce the estimation bias [15]. We test the net policy effect by using the ORDP as a semi-natural experiment. By doing this, we can lessen the endogeneity problem posed by omitted variables that affect both ORDP and economic growth.

## Data and method

### Data and variables
Before conducting empirical test, the Nighttime Satellite Light Data, ORDP data, and other variables influencing economic growth are manually collected. The final sample is made up of data from 78 cities spread throughout three old revolutionary areas from 2013 to 2019.

We use a sample of 78 prefecture-level cities located in three ORBAs because they implemented ORDP after 2013. Specifically, Sichuan-Shaanxi implemented ORDP in August 2016, Dabie Mountain ORDP was implemented in July 2015, and the Left and Right River ORDP was executed in March 2015. The reasons why we select the period from 2013 to 2019 as our sample are as follows. First, the VIIRS/DNB Nighttime Satellite Light Data is only available since 2013. Second, most data after 2019 is inaccessible due to data availability.

The VIIRS/DNB Nighttime Satellite Light Data is used to measure economic growth. These data come from the China Research Data Service Platform (CNRDS). To decrease heteroscedasticity, nightlight values are converted to a natural logarithmic form.

If ORDP is implemented in city i of year t, then we define ORDP for the city in year t and subsequent years as 1, and 0 otherwise.

Based on existing studies, our research chooses a set of control variables to control possible factors that may impact economic growth. Consequently, five control variables are selected: consumption, population density, human capital, financial development, and foreign investment. Consumption is defined as the proportion of total social consumption to GDP. Population density is population per square kilometer in logarithmic form; the relation between population density and economic growth is not linear but inverted U-shaped [41]. Human capital is defined as the total number of college students. Financial development is determined by the proportion of the year-end loanable fund to GDP. Foreign investment is measured using the natural logarithm of foreign direct investment (FDI).

The China City Statistical Yearbook and the China Provincial Statistical Yearbook are the sources of all these indicators. The average growth rate is used to supplement the missing data. Consequently, the panel data of 546 samples of 78 cities from 2013 to 2019 are finally derived.

### Model: Time-varying DID method
Endogenous problem is a great challenge for policy effect identification, and DID model can eliminate the endogenous problem by comparing the group affected by the policy to that unaffected over time [46]. Therefore, we apply a DID method to assess the possible relation between ORDP and economic growth. Considering the different implementation times of ORDP, we employ the time-varying DID method, which enables us to control for time-variant, city-level omitted characteristics by including city-specific dummy variables [47].

nightlight it is a proxy variable of economic growth of city i in year t. If city i implemented ORDP in year t, ORDP it equals 1, and 0 otherwise. Therefore, alpha1 assesses the net impact of ORDP on economic growth. If alpha1 is positive and significant, it suggests that ORDP increases economic growth. Xit represents the control variables. delta i reflects the city-fixed effect and theta t is the year-fixed effect.

After estimating the average treatment effect of ORDP on economic growth, we examine the dynamic treatment effect and test the common trend assumption.

## Empirical results
We first perform the common trend test and then demonstrate the ORDP's average treatment effect on economic growth, followed by a dynamic treatment effect of ORDP. We also conduct seven robustness tests to verify the robustness of base results. Then, three possible mechanisms of ORDP on economic growth are investigated. Finally, we evaluate the heterogeneous effects of ORDP on economic growth.

### Common trend test
Before using the DID approach to estimate the ORDP's effect on economic growth, we should pre-test whether the economic growth in ORDP and non-ORDP cities shows a common trend prior to ORDP being implemented. As shown in Fig 2, we can find that before the city implements the ORDP, the estimated coefficients of ORDP are all insignificantly different from zero, meeting the common trend assumption.

### The average treatment effect of ORDP on economic growth
The average treatment effect of ORDP on economic growth is shown in Table 1. It can be found that ORDP significantly facilitates economic growth by 4.0%. Therefore, we conclude that ORDP can increase economic development in ORDP areas, which verifies our Hypothesis 1.

### The dynamic treatment effect of ORDP on economic growth
From a static perspective, the benchmark regression shows that ORDP significantly and positively affects economic growth, however, if this impact will be long-lasting is unclear. Thus, we identify dynamic treatment effects and Table 2 shows the results. According to the results, we can conclude that the policy effect of ORDP takes time to emerge and is not long-lasting. Specifically, the coefficient of ORDP1 is not significant, suggesting that in the first year after ORDP implementation, there is no impact on economic progress. However, the positive trend of ORDP's impact on economic growth is not sustainable, as ORDP4's coefficient (0.175) is smaller than that of ORDP3 (0.214).

### Robustness tests
We also conduct several robustness tests. These specifically include the following seven: a placebo test, replacing the dependent variable with real per capita GDP, excluding the impact of TPA policy, excluding the provincial and sub-provincial cities, using the propensity score matching and the difference-in-differences model (PSM-DID), changing the sample period, and excluding the effect of outliers.

We further carried out two placebo tests to see if our baseline regression results excluded random probability. One placebo examination is conducted counterfactual time. Specifically, we advance the ORDP implementation year by 1 year to construct a false ORDP implementation time. If the coefficient of false ORDP is insignificant, then the economic growth is indeed caused by ORDP. We conduct counterfactual samples as the second placebo test. Following Raj et al. [49], we choose 18 cities at random to represent the pseudo-ORDP group and the remaining as the non-ORDP group, then run regression based on the counterfactual ORDP samples. To improve reliability, we repeat the procedure 500 times and record the estimated parameters.

We replace the VIIRS/DNB nightlight value with real per capita GDP to evaluate economic growth, since it is a common measurement of economic growth by scholars. After the replacement of the dependent variable, the coefficient of ORDP is still significantly positive.

In 2014, a place-based policy in China, the Targeted Poverty Alleviation (TPA) Policy was also proposed in addition to the ORDP. Not only was the TPA policy implemented at roughly the same time as ORDP, but many of the TPA cities also matched the ORDP cities. To improve the accuracy of our baseline result, we need to exclude the impact of the TPA policy. We construct the model by adding TPA policy as a dummy variable to our benchmark DID model. The symbol and significance of ORDP it are in line with the outcome of our baseline model, indicating the accuracy of our estimates.

The potential factors affecting economic development may vary depending on the city's administrative hierarchy, thus leading to a biased estimation of the net policy effect [50]. After removing six provincial and sub-provincial cities, we performed regression. We can discover that the ORDP's coefficient slightly lowers but remains statistically significantly positive.

The combination of PSM and DID methods is first proposed by James et al. [52] to identify control groups. First, the propensity score is computed based on the logit model for each sample. Second, the ORDP city is matched to the non-ORDP city by using the 1 nearest neighbor matching method. Third, carrying out the common value test as well as the matching balance test. We can see that all control variables' standardized deviations are less than 20% after matching than they were before, showing that the matching meets the balance test. Finally, after passing the common value and matching balance test, we then re-estimate the net policy effects using the matched samples. It can be found that ORDP still significantly boosts economic growth by 5.7%.

In order to eliminate the possible influence of the COVID-19 pandemic in 2019, we shorten the time interval from 2013-2019 to 2014-2018. The coefficients on ORDP remain significantly positive.

Extreme values are another potential issue that could jeopardize the benchmark findings. The histograms of data reveal that the outliers are generally distributed on the right side of the data set. Therefore, we winsorize the up 1%, 3%, and 5% of the samples and repeat the benchmark regression. The coefficients of ORDP are comparable to the baseline findings.

### Mechanism analysis
The above results have proven that ORDP can boost economic growth. However, what mechanism behind ORDP remains to be answered. To check these three possible mechanisms, in accordance with Baron et al. [54], the following method is developed. Mit represents three mediation variables: government intervention, industrial structure optimization, and information infrastructure construction. We use the ratio of government expending to GDP to stand for government intervention. Regarding industrial structure optimization, we use the industrial structure upgrading index. The natural logarithm of the number of internet access users denotes the level of information infrastructure.

We judge whether there is a mediation effect according to the following three steps. First, assess the overall effect alpha1, and if it is significant, move on to the next step. Second, test beta1 and tau2. In case both coefficients are significant, test tau1. A significant tau1 indicates a partial mediation effect, while a non-significant tau1 indicates a full mediation effect. Third, in the case that at least one of beta1 and tau2 is insignificant, the Sobel test is executed.

### Heterogeneity analysis
Policy effects often diverge due to variations in economic status, resource endowment, human capital, and other factors. Therefore, the conclusions of the baseline regression must be examined for heterogeneity. Following Yang et al. [4], we classify cities into central and western regions based on their geographic location. We can see that the central region's ORDP coefficient is significantly positive, with or without the control variables. Contrarily, the western region's ORDP coefficient, albeit positive, is not significant, indicating that ORDP does not influence the western region's economy.

We use per capita GDP as a criterion to classify cities into high economic level cities and low economic level cities. ORDP's coefficient in high economic level cities (0.058) is significant at 10%, while the coefficient of ORDP in low economic level cities (0.046) is insignificant.

## Conclusions
Whether place-based policy can improve economic growth or not has been debated for several decades. In this paper, after selecting 78 prefecture-level cities in the scope of ORDP areas from 2013 to 2019, we study the net impact of ORDP on economic performance using a time-varying DID model. First, ORDP can boost economic growth by 4.01%, but the impact takes a period to emerge and can't sustain in the long run. The results are reliable after seven robustness tests. Second, expanding government intervention, optimizing industrial structure, and improving information infrastructure construction are three working mechanisms. Third, heterogeneity analysis illustrates that ORDP performs better on economic growth in central China cities and high-economy cities.

## References
[1] Pan D, Zhou P, Kong F. Effect of place-based policy on regional economic growth: A quasi-natural experiment from China's Old Revolutionary Development Program. PLoS ONE. 2023;18(7):e0288901.
