############################
# programForecastClasso.R
#
# Last modified: 13-Jun-2024
############################

#################
# Define function
#################

estimateLassoGr = function(x,
                           y,
                           valueWeight){

  # Fit model via glmnet
  fit = glmnet(x = x,
               y = y,
               weights = valueWeight,
               alpha = 1,
               lower.limits = 0,
               standardize = FALSE)

  # Coefficients
  b = as.matrix(coef(fit, exact = TRUE))

  # Storage vector - corrected AIC
  aicc = rep(NA, length(fit$lambda))

  # Iterate over lambda values
  for ( k in 1:length(fit$lambda) ){

    # No predictors selected
    if ( sum(b[ -1 , k ]) == 0 ){

      # Degrees of freedom
      kDf = 0

    # At least one predictor selected
    } else if ( sum(b[ -1 , k ]) != 0 ){

      # Degrees of freedom
      kDf = fit$df[ k ]
      
    }

    # Fitted residual     
    kResid = y - cbind(rep(1, length(y)), x) %*% b[ , k ]

    # Degrees-of-freedom term
    kDfTerm = 2*kDf*length(y)/(length(y) - kDf)

    # Update vector
    aicc[ k ] = length(y)*log(mean(valueWeight*(kResid^2))) + kDfTerm

  }

  # Optimal coefficient vector
  b = b[ , which.min(aicc) ]

  return(b)

}

################
# Load forecasts
################

# Univariate predictive regression forecasts
forecastUni = readRDS('forecastUni.RDS')

# Extract date vector
date = unique(forecastUni$date)

# Number of time-series observations
T = length(date)

########################################
# Compute weights based on market equity
########################################

# Iterate over months (parallel computing)
f = function(t){

  # Month-t data
  tForecastUni = forecastUni[ forecastUni$date == date[ t ] , ]

  # Month-t weights (scale to sum to one)
  tWeight = data.frame(tForecastUni$date,
                       tForecastUni$permno,
                       tForecastUni$me/sum(tForecastUni$me))

  # Clean up variable names
  names(tWeight) = c('date',
                     'permno',
                     'weight')

  return(tWeight)

}

# Compute monthly weights via parallel computing
weight = mclapply(1:T,
                  f,
                  mc.cores = coreNumber)

#########################################################
# Estimate cross-sectional Granger-Ramanathan regressions
#########################################################

# Iterate over months (parallel computing)
f = function(t){

  # Storage vector - GR coefficients
  tCoefGr = rep(NA, J)

  # Month-t univariate forecasts
  tForecastUni = forecastUni[ forecastUni$date == date[ t ] , ]

  # Month-t weights
  tWeight = weight[[ t ]]

  # Weights (based on market equity)
  tWeight = as.matrix(tWeight[ , 'weight' ])

  # Scale weights to sum to number of observations
  tWeight = tWeight/mean(tWeight)

  # Data matrix - cross-sectional GR regression
  tDataGr = tForecastUni[ , -(1:length(nameFront)) ]

  # Indices - non-NA forecasts
  tIndex = which(!is.na(tDataGr[ 1 , ]))

  # Last month
  if ( t == T ){

    # Usable univariate forecasts
    tDataGr = as.matrix(tDataGr[ , tIndex ])

  # Not in last month
  } else {

    # Month-(t+1) univariate forecasts
    tPlusOneForecastUni = forecastUni[ forecastUni$date == date[ t+1 ] , ]

    # Data matrix - cross-sectional GR regression
    tPlusOneDataGr = tPlusOneForecastUni[ , -(1:length(nameFront)) ]

    # Indices - non-NA forecasts
    tPlusOneIndex = which(!is.na(tPlusOneDataGr[ 1 , ]))

    # Indices - usable forecasts
    tIndex = intersect(tIndex,
                       tPlusOneIndex)

    # Usable univariate forecasts
    tDataGr = as.matrix(tDataGr[ , tIndex ])

  }

  # Fit month-t cross-sectional GR regression via the LASSO
  tCoef = estimateLassoGr(x = tDataGr,
                          y = tForecastUni$ret,
                          valueWeight = tWeight)

  # Convert to vector
  tCoef = as.numeric(tCoef[ -1 ])

  # Update vector
  tCoefGr[ tIndex ] = tCoef[ -1 ]

  return(tCoefGr)

}

# Compute monthly GR coefficient estimates via parallel computing
coefGr = mclapply(1:T,
                  f,
                  mc.cores = coreNumber)

# Convert list object to data frame
coefGr = list.rbind(coefGr)

# Include date variable
coefGr = data.frame(date,
                    coefGr)

# Clean up variable names
names(coefGr) = c('date',
                  nameChar)

# Save data frame
saveRDS(coefGr,
        'coefGr.RDS')

# Drop date variable for next block
coefGr = coefGr[ , -1 ]

##################################################
# Compute monthly cross-sectional return forecasts
##################################################

# Iterate over months (parallel computing)
f = function(t){

  # Month-t univariate forecasts
  tForecastUni = forecastUni[ forecastUni$date == date[ t ] , ]

  # Data matrix - cross-sectional GR regression
  tDataGr = tForecastUni[ , -(1:length(nameFront)) ]

  # Indices - non-NA forecasts
  tIndex = which(!is.na(tDataGr[ 1 , ]))

  # Month-(t+1) univariate forecasts
  tPlusOneForecastUni = forecastUni[ forecastUni$date == date[ t+1 ] , ]

  # Data matrix - cross-sectional GR regression
  tPlusOneDataGr = tPlusOneForecastUni[ , -(1:length(nameFront)) ]

  # Indices - non-NA forecasts
  tPlusOneIndex = which(!is.na(tPlusOneDataGr[ 1 , ]))

  # Indices - usable forecasts
  tIndex = intersect(tIndex,
                     tPlusOneIndex)

  # Usable univariate forecasts
  tPlusOneDataGr = as.matrix(tPlusOneDataGr[ , tIndex ])

  # Indices - selected univariate forecasts
  tIndexCombine = which(coefGr[ t , tIndex ] != 0)

  # No univariate forecast selected
  if ( length(tIndexCombine) == 0 ){

    # Combination forecast
    tPlusOneForecast = rep(0, nrow(tPlusOneDataGr))

  # At least one predictor selected
  } else {

    # One univariate forecast selected
    if ( length(tIndexCombine) == 1 ){

      # Combination forecast
      tPlusOneForecast = tPlusOneDataGr[ , tIndexCombine ]

    # Multiple univariate forecasts selected
    } else {

      # Combination forecast
      tPlusOneForecast = apply(tPlusOneDataGr[ , tIndexCombine ], 1, mean)

    }

  }

  # Create data frame
  tPlusOneForecast = data.frame(tPlusOneForecastUni[ , nameFront ],
                                tPlusOneForecast)

  # Clean up variable names
  names(tPlusOneForecast) = c(nameFront,
                              'forecast')

  return(tPlusOneForecast)

}

# Compute combination forecast via parallel computing
forecast = mclapply(1:(T-1),
                    f,
                    mc.cores = coreNumber)

# Convert list object to data frame
forecast = list.rbind(forecast)

# Save data frame
saveRDS(forecast,
        'forecastClasso.RDS')

# Free some memory
rm(forecastUni,
   weight,
   coefGr,
   forecast)
