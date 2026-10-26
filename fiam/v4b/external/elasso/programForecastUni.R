############################
# programForecastUni.R
#
# Last modified: 13-Jun-2024
############################

##################################################
# Compute monthly cross-sectional return forecasts
##################################################

# Intercepts - univariate predictive regressions
coefIntercept = readRDS('coefUniIntercept.RDS')

# Slopes - univariate predictive regressions
coefSlope = readRDS('coefUniSlope.RDS')

# Iterate over months (parallel computing)
f = function(t){

  # Month-t data
  tData = data[ data$date == date[ t ] , ]

  # Characteristic data
  tDataChar = tData[ , !(names(tData) %in% nameFront) ]

  # Indices - usable characteristics
  tIndex = which(apply(tDataChar, 2, function(x) sum(is.na(x))) == 0)

  # Month-(t+1) data
  tPlusOneData = data[ data$date == date[ t+1 ] , ]

  # Returns
  tPlusOneRet = tPlusOneData[ , 'ret' ]

  # Vector of ones (for intercept)
  tPlusOneIota = rep(1, nrow(tPlusOneData))

  # Characteristic data
  tPlusOneDataChar = tPlusOneData[ , !(names(tPlusOneData) %in% nameFront) ]

  # Indices - usable characteristics
  tPlusOneIndex = which(apply(tPlusOneDataChar, 2,
                              function(x) sum(is.na(x))) == 0)

  # Indices - common characteristics in months t & t+1
  tIndex = intersect(tIndex,
                     tPlusOneIndex)

  # Usable characteristic data
  tPlusOneZ = as.matrix(tPlusOneDataChar[ , tIndex ])

  # Storage matrix - univariate forecasts
  tPlusOneForecast = matrix(NA, nrow(tPlusOneData), J)

  # Iterate over characteristics
  for ( j in 1:length(tIndex) ){

    # Coefficient vector
    tjCoef = c(coefIntercept[ t , tIndex[ j ]+1 ],
               coefSlope[ t , tIndex[ j ]+1 ])

    # Univariate predictive regression forecast
    tPlusOneForecast[ , tIndex[ j ] ] =
      cbind(tPlusOneIota, tPlusOneZ[ , j ]) %*% tjCoef

  }

  # Create data frame
  tPlusOneForecast = data.frame(tPlusOneData[ , c('date',
                                                  'permno',
                                                  'exchcd',
                                                  'me')],
                                tPlusOneRet,
                                tPlusOneForecast)

  # Clean up variable names
  names(tPlusOneForecast) = c('date',
                              'permno',
                              'exchcd',
                              'me',
                              'ret',
                              nameChar)

  return(tPlusOneForecast)

}

# Compute monthly forecasts via parallel computing
forecast = mclapply(1:(T-1),
                    f,
                    mc.cores = coreNumber)

# Convert list object to data frame
forecast = list.rbind(forecast)

# Save data frame
saveRDS(forecast,
        'forecastUni.RDS')

# Free some memory
rm(coefIntercept,
   coefSlope,
   forecast)
