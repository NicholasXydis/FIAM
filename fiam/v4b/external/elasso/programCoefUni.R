############################
# programCoefUni.R
#
# Last modified: 13-Jun-2024
############################

########################################
# Compute weights based on market equity
########################################

# Iterate over months (parallel computing)
f = function(t){

  # Month-t data
  tData = data[ data$date == date[ t ] , ]

  # Month-t weights (scale to sum to one)
  tWeight = data.frame(tData$date,
                       tData$permno,
                       tData$me/sum(tData$me))

  # Clean up variable names
  names(tWeight) = c('date',
                     'permno',
                     'weight')

  return(tWeight)

}

# Compute weights via parallel computing
weight = mclapply(1:T,
                  f,
                  mc.cores = coreNumber)

############################################
# Estimate univariate predictive regressions
############################################

# Iterate over months (parallel computing)
f = function(t){

  # Storage matrix - univariate coefficients (intercept/slope)
  tCoef = matrix(NA, J, 2)

  # Month-t data
  tData = data[ data$date == date[ t ] , ]

  # Month-t weights
  tWeight = weight[[ t ]]

  # Number of observations
  tI = nrow(tData)

  # Weights (based on market equity)
  tWeight = tWeight[ , 'weight' ]

  # Scale weights to sum to number of observations
  tWeight = tWeight/mean(tWeight)

  # Returns
  tRet = tData[ , 'ret'  ]

  # Characteristic data
  tDataChar = tData[ , !(names(tData) %in% nameFront) ]

  # Free some memory
  rm(tData)

  # Indices - usable characteristics
  tIndex = which(apply(tDataChar, 2, function(x) sum(is.na(x))) == 0)

  # Last month
  if ( t == T ){

    # Usable characteristic data
    tZ = as.matrix(tDataChar[ , tIndex ])

  # All months but last
  } else if ( t < T ){

    # Month-(t+1) data
    tPlusOneData = data[ data$date == date[ t+1 ] , ]

    # Characteristic data
    tPlusOneDataChar = tPlusOneData[ , !(names(tPlusOneData) %in% nameFront) ]

    # Free some memory
    rm(tPlusOneData)

    # Indices - usable characteristics
    tPlusOneIndex = which(apply(tPlusOneDataChar, 2,
                                function(x) sum(is.na(x))) == 0)

    # Indices - common characteristics
    tIndex = intersect(tIndex,
                       tPlusOneIndex)

    # Usable characteristic data
    tZ = as.matrix(tDataChar[ , tIndex ])

  }

  # Iterate over characteristics - univariate predictive regressions
  for ( j in 1:length(tIndex) ){

    # Fit month-t univariate predictive regression via WLS
    tCoef[ tIndex[ j ] , ] = lm(tRet ~ tZ[ , j ],
                                weights = tWeight)$coefficients

  }
  
  return(tCoef)

}

# Compute coefficients via parallel computing
coef = mclapply(1:T,
                f,
                mc.cores = coreNumber)

# Storage matrix - univariate intercepts
coefIntercept = matrix(NA, T, J)

# Storage matrix - univariate slope coefficients
coefSlope = matrix(NA, T, J)

# Iterate over months
for ( t in 1:T ){

  # Update matrix - univariate intercepts
  coefIntercept[ t , ] = coef[[ t ]][ , 1 ]

  # Update matrix - univariate slope coefficients
  coefSlope[ t , ] = coef[[ t ]][ , 2 ]

}

# Data frame with date variable
coefIntercept = data.frame(date,
                           coefIntercept)

# Clean up variable names
names(coefIntercept) = c('date',
                         nameChar)

# Save data frame
saveRDS(coefIntercept,
        'coefUniIntercept.RDS')

# Data frame with date variable
coefSlope = data.frame(date,
                       coefSlope)

# Clean up variable names
names(coefSlope) = c('date',
                     nameChar)

# Save data frame
saveRDS(coefSlope,
        'coefUniSlope.RDS')

# Free some memory
rm(weight,
   coef,
   coefIntercept,
   coefSlope)
