############################
# programForecastSlasso.R
#
# Last modified: 11-Jun-2024
############################

#################
# Define function
#################

computeAvg = function(x,
                      sizeAvg){

  # Convert to matrix format
  x = as.matrix(x)

  # Fewer observations than MA length
  if ( nrow(x) < sizeAvg ){

    # Only one variable
    if ( ncol(x) == 1 ){

      # Mean (scalar)
      xBar = mean(x, na.rm = TRUE)

    # More than one variable
    } else {

      # Vector of means
      xBar = apply(x, 2, mean, na.rm = TRUE)

    }

  # More observations than MA length
  } else {

    # Only one variable
    if ( ncol(x) == 1 ){

      # Mean (scalar)
      xBar = mean(x[ (nrow(x)-(sizeAvg-1)):nrow(x) ], na.rm = TRUE)

    # More than one variable
    } else{

      # Vector of means
      xBar = apply(x[ (nrow(x)-(sizeAvg-1)):nrow(x) , ], 2, mean, na.rm = TRUE)

    }

  }

  return(xBar)

}

##########################################
# Compute cross-sectional return forecasts
##########################################

# LASSO coefficients
coef = readRDS('coefLasso.RDS')

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
  tPlusOneRet = as.matrix(tPlusOneData[ , 'ret' ])

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

  # Storage matrix
  tPlusOneForecast = matrix(NA, length(tPlusOneRet), length(vecSizeMa))

  # Iterate over MA lengths
  for ( i in 1:length(vecSizeMa) ){

    # No smoothing
    if ( vecSizeMa[ i ] == 1 ){

      # Coefficient vector
      tCoef = coef[ t , c(2, tIndex+2) ]

      # LASSO forecast
      tPlusOneForecast[ , i ] = cbind(tPlusOneIota, tPlusOneZ) %*% t(tCoef)

    # Smoothing
    } else {

      # Coefficient vector
      tCoef = computeAvg(coef[ 1:t , c(2, tIndex+2) ],
                         vecSizeMa[ i ])

      # LASSO forecast
      tPlusOneForecast[ , i ] = cbind(tPlusOneIota, tPlusOneZ) %*% tCoef

    }

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
                              nameSizeMa)

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
        'forecastSlasso.RDS')

# Free some memory
rm(coef,
   forecast)
