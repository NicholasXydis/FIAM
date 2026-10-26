############################
# programForecastElasso.R
#
# Last modified: 13-Jun-2024
############################

##################
# Define functions
##################

computeAvg = function(x,
                      sizeAvg){

  # Convert to matrix format
  x = as.matrix(x)

  # More observations than MA length
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

  # Fewer observations than MA length
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

regressEncompass = function(forecastA,
                            forecastB,
                            actual,
                            valueWeight){

  # Forecast error - A
  eA = actual - forecastA

  # Forecast error - B
  eB = actual - forecastB

  # Difference in forecast errors
  d = eA - eB

  # Fit Harvey, Leybourne & Newbold (1998) regression via OLS
  b = lm(eA ~ d,
         weights = valueWeight)$coefficients[ -1 ]

  # Enforce lower bound
  if ( b < 0 ){

    # Lower bound
    b = 0

  # Enforce upper bound
  } else if ( b > 1 ){

    # Upper bound
    b = 1

  }

  return(b)

}

################
# Load forecasts
################

# S-LASSO forecast
forecastSlasso = readRDS('forecastSlasso.RDS')

# C-LASSO forecast
forecastClasso = readRDS('forecastClasso.RDS')

# Extract date vector
date = unique(forecastClasso$date)

# Number of time-series observations
T = length(date)

# Drop first month
forecastSlasso = forecastSlasso[ forecastSlasso$date >= date[ 1 ] , ]

########################################
# Compute weights based on market equity
########################################

# Iterate over months (parallel computing)
f = function(t){

  # Month-t data
  tForecastSlasso = forecastSlasso[ forecastSlasso$date == date[ t ] , ]

  # Month-t weights (scale to sum to one)
  tWeight = data.frame(tForecastSlasso$date,
                       tForecastSlasso$permno,
                       tForecastSlasso$me/sum(tForecastSlasso$me))

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

###################################
# Compute encompassing coefficients
###################################

# Iterate over months (parallel computing)
f = function(t){
  
  # Month-t data - forecast A
  tForecastA = forecastSlasso[ forecastSlasso$date == date[ t ] , ]
  
  # Month-t data - forecast B
  tForecastB = forecastClasso[ forecastClasso$date == date[ t ] , ]

  # Encompassing regression
  tCoefEncompass = regressEncompass(forecastA = tForecastA$MaInf,
                                    forecastB = tForecastB$forecast,
                                    actual = tForecastA$ret,
                                    valueWeight = weight[[ t ]]$weight)

  return(tCoefEncompass)

}

# Compute encompassing coefficient
coefEncompassMa1 = mclapply(1:T,
                            f,
                            mc.cores = coreNumber)

# Combine to vector
coefEncompassMa1 = as.numeric(list.rbind(coefEncompassMa1))

# Storage matrix - encompassing coefficient
coefEncompass = matrix(NA, T, length(vecSizeMa))

# Update matrix - no smoothing
coefEncompass[ , 1 ] = coefEncompassMa1

# Iterate over months
for ( t in 1:T ){

  # Iterate over MA lengths (>1)
  for ( i in 2:length(vecSizeMa) ){

    # Update matrix - smoothing
    coefEncompass[ t , i ] = computeAvg(coefEncompass[ 1:t , 1 ],
                                        vecSizeMa[ i ])

  }

}

# Create data frame
coefEncompass = data.frame(date,
                           coefEncompass)

# Clean up variable names
names(coefEncompass) = c('date',
                         nameSizeMa)

# Save data frame
saveRDS(coefEncompass,
        'coefEncompass.RDS')

##################################################
# Compute monthly cross-sectional return forecasts
##################################################

# Iterate over months (parallel computing)
f = function(t){

  # Month-(t+1) forecast
  tPlusOneForecastA =
    forecastSlasso[ forecastSlasso$date == date[ t+1 ] , 'MaInf' ]

  # Month-(t+1) forecast
  tPlusOneForecastB =
    forecastClasso[ forecastClasso$date == date[ t+1 ] , 'forecast' ]

  # Storage matrix - encompassing forecast
  tPlusOneForecast = matrix(NA,
                            length(tPlusOneForecastA),
                            length(vecSizeMa))

  # Iterate over MA lengths
  for ( i in 1:length(vecSizeMa) ){

    # Encompassing forecast
    tPlusOneForecast[ , i ] =
      (1 - coefEncompass[ t , i+1 ])*tPlusOneForecastA +
      coefEncompass[ t , i+1 ]*tPlusOneForecastB

  }

  # Create data frame
  tPlusOneForecast =
    data.frame(forecastSlasso[ forecastSlasso$date == date[ t+1 ] ,
                               nameFront ],
               tPlusOneForecast)

  # Clean up variable names
  names(tPlusOneForecast) = c(nameFront,
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
        'forecastElasso.RDS')

# Free some memory
rm(forecastSlasso,
   forecastClasso,
   weight,
   coefEncompass,
   forecast)
