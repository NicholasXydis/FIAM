############################
# programEvaluateForecast.R
#
# Last modified: 13-Jun-2024
############################

############################
# Take care of preliminaries
############################

# Name - selected forecast (appears after 'forecast' in the file name for the
# RDS file with the forecasts)
nameForecast = 'Elasso'

# Names - front-matter variables (should appear as first five variables in the
# data frame with the forecast variables following)
nameFront = c('date',
              'permno',
              'exchcd',
              'me',
              'ret')

# Out-of-sample period start date
dateOutStart = as.Date('1970-01-01')

# Out-of-sample period end date
dateOutEnd = as.Date('2021-12-01')

# Number of cores - mclapply argument (parallel computing)
coreNumber = 16

###############
# Load packages
###############

library(sandwich)
library(parallel)

##################
# Define functions
##################

evaluateForecast = function(forecast,
                            actual,
                            valueWeight){
  
  # Forecast deviation from weighted mean
  forecastDev = forecast - mean(valueWeight*forecast)

  # Realized deviation from weighted mean
  actualDev = actual - mean(valueWeight*actual)

  # Forecast weighted volatility
  volForecast = sqrt(mean(valueWeight*forecastDev^2))

  # Realized weighted volatility
  volActual = sqrt(mean(valueWeight*actualDev^2))

  # Weighted mean squared forecast error
  wMsfe = mean(valueWeight*(actualDev-forecastDev)^2)

  # Benchmark (zero forecast) mean squared forecast error
  wMsfeBench = mean(valueWeight*actualDev^2)

  # Cross-sectional out-of-sample R-squared statistic
  r2csos = 100*(1 - wMsfe/wMsfeBench)

  # Fit cross-sectional Mincer-Zarnowitz regression via WLS
  fitMz = lm(actual ~ forecast,
             weights = valueWeight)

  # Cross-sectional Mincer-Zarnowitz slope coefficient
  b = fitMz$coefficients[ -1 ]

  # Cross-sectional Mincer-Zarnowitz R-squared statistic
  r2csmz = 100*summary(fitMz)$r.squared

  # Difference in weighted MSFE
  dMsfe = wMsfeBench - wMsfe

  # Output vector
  stat = c(volForecast,
           volActual,
           r2csos,
           b,
           r2csmz,
           dMsfe)

  return(stat)

}

estimateConstantOnly = function(y, h){

  # Fit regression with constant only via OLS
  fit = lm(y ~ 1)

  # Intercept estimate
  b = fit$coefficients

  # HAC variance
  v = NeweyWest(fit,
                lag = h-1)

  # HAC t-statistic for testing b = 0
  tstat0 = b/sqrt(v)

  # HAC t-statistic for testing b = 1
  tstat1 = (b - 1)/sqrt(v)

  # Output vector
  result = c(b,
             tstat0,
             tstat1)

  return(result)

}

computeFm = function(volForecast,
                     volActual,
                     r2csos,
                     b,
                     r2csmz,
                     h){
  
  # Time-series average
  resultR2csos = estimateConstantOnly(r2csos, h)

  # Time-series average
  resultSlope = estimateConstantOnly(b, h)

  # Time-series average
  resultR2csmz = estimateConstantOnly(r2csmz, h)

  # Collect results
  result = c(mean(volForecast),
             mean(volActual),
             resultR2csos[ 1:2 ],
             resultSlope,
             resultR2csmz[ 1 ])

  return(result)

}

###############
# Load forecast
###############

# Load selected forecast
forecast = readRDS(paste0('forecast',
                          nameForecast,
                          '.RDS'))

# Out-of-sample data
forecast = forecast[ forecast$date >= dateOutStart &
                       forecast$date <= dateOutEnd, ]

# Extract date vector
date = unique(forecast$date)

# Forecast horizon
h = 1

# Names - individual forecasts
nameForecastInd = names(forecast)[ -(1:length(nameFront)) ]

############################################
# Evaluate monthly cross-sectional forecasts
############################################

# Names - out-of-sample statistics
nameStat = c('volForecast',
             'volActual',
             'r2csos',
             'b',
             'r2csmz',
             'dMsfe')

# Iterate over out-of-sample months (parallel computing)
f = function(t){

  # Storage matrix
  tResult = matrix(NA, length(nameStat), length(nameForecastInd))

  # Month-t forecasts
  tForecast = forecast[ forecast$date == date[ t ] , ]

  # Month-t weights
  tWeight = tForecast$me

  # Scale weights to sum to number of observations
  tWeight = tWeight/mean(tWeight)

  # Iterate over individual forecasts
  for ( i in 1:length(nameForecastInd) ){

    # MA length-i, month-t forecast
    itForecast = tForecast[ , nameForecastInd[ i ] ]

    # Out-of-sample statistics
    tResult[ , i ] = evaluateForecast(forecast = itForecast,
                                      actual = tForecast$ret,
                                      valueWeight = tWeight)

  }

  return(tResult)

}

# Compute monthly out-of-sample statistics via parallel computing
result = mclapply(1:length(date),
                  f,
                  mc.cores = coreNumber)

#########################
# Collect monthly results
#########################

# Storage data frame - out-of-sample statistics
stat = data.frame(date,
                  matrix(NA, length(date), length(nameStat)))

# Variable names
names(stat) = c('date',
                nameStat)

# Storage list object
stat = rep(list(stat),
           times = length(nameForecastInd))

# Object names
names(stat) = nameForecastInd

# Iterate over individual forecasts
for ( i in 1:length(nameForecastInd) ){

  # Iterate over months
  for ( t in 1:length(date) ){

    # Month-t results
    tResult = result[[ t ]]

    # Month-t, forecast-i statistics
    stat[[ i ]][ t , -1 ] = result[[ t ]][ , i ]

  }

  # Save as RDS file
  saveRDS(stat[[ i ]],
          paste0('stat',
                 nameForecast,
                 '.RDS'))

}

# Free some memory
rm(result)

##############################
# Compute time-series averages
##############################

# Names - out-of-sample statistics
nameTsa = c('volFc',
            'volActual',
            'r2csos',
            't0',
            'slope',
            't0',
            't1',
            'r2csmz')

# Storage data frame - time-series averages
tsa = as.data.frame(matrix(NA, length(nameForecastInd), length(nameTsa)))

# Clean up variable names
names(tsa) = nameTsa

# Iterate over individual forecasts
for ( i in 1:length(nameForecastInd) ){

  # Compute time-series averages
  tsa[ i , ] = computeFm(stat[[ i ]]$volForecast,
                         stat[[ i ]]$volActual,
                         stat[[ i ]]$r2csos,
                         stat[[ i ]]$b,
                         stat[[ i ]]$r2csmz,
                         h)

}

# Forecast results
tsa = as.table(round(as.matrix(tsa), 2))

# Row names
rownames(tsa) = nameForecastInd

cat('\nOut-of-sample statistics\n\n')

print(tsa)

###############################################
# Cumulative difference in cross-sectional MSFE
###############################################

# Difference in MSFE - first forecast
dMsfe = stat[[ 1 ]][ , 'dMsfe' ]

# Iterate over remaining individual forecast
for ( i in 2:length(nameForecastInd) ){
  
  # Horizontal concatenation
  dMsfe = cbind(dMsfe,
                stat[[ i ]][ , 'dMsfe' ])
}

# Cumulative difference in MSFE
cdmsfe = apply(dMsfe, 2, cumsum)

# Data frame with date variable
cdmsfe = data.frame(date,
                    cdmsfe)

# Clean up variable names
names(cdmsfe) = c('date',
                  nameForecastInd)

# Save as RDS file
saveRDS(cdmsfe,
        'cdmsfeElasso.RDS')

# Free some memory
rm(stat,
   cdmsfe)

###############################################
# Encompassing test (comment out if not needed)
###############################################

# Load encompassing coefficients
coefEncompass = readRDS('coefEncompass.RDS')

# Drop observations/variables
coefEncompass = matrix(coefEncompass[ coefEncompass$date >= dateOutStart ,
                                      2 ])

# Fit regression with constant only via OLS
fit = lm(coefEncompass ~ 1)

# Intercept estimate
b = fit$coefficients

# HAC variance
v = NeweyWest(fit,
              lag = h-1)

# HAC t-statistic for testing b = 0
tstat0 = b/sqrt(v)

# HAC t-statistic for testing b = 1
tstat1 = (b - 1)/sqrt(v)

# Output vector
result = c(b,
           tstat0,
           tstat1)

cat('\nEncompassing test results\n\n', round(result,2))
