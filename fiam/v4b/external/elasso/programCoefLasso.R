############################
# programCoefLasso.R
#
# Last modified: 13-Jun-2024
############################

#################
# Define function
#################

estimateLasso = function(x,
                         y,
                         valueWeight){

  # Fit model via glmnet
  fit = glmnet(x = x,
               y = y,
               weights = valueWeight,
               alpha = 1,
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

###############################################
# Estimate predictive regressions via the LASSO
###############################################

# Iterate over months (parallel computing)
f = function(t){

  # Storage vector - LASSO coefficients
  tCoef = rep(NA, J+1)

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

  # Fit predictive regression via the LASSO
  tFit = estimateLasso(x = tZ,
                       y = tRet,
                       valueWeight = tWeight)

  # Update vector
  tCoef[ c(1, tIndex+1) ] = tFit

  return(tCoef)

}

# Compute coefficients via parallel computing
coefLasso = mclapply(1:T,
                     f,
                     mc.cores = coreNumber)

# Combine list into matrix
coefLasso = list.rbind(coefLasso)

# Data frame with date variable
coefLasso = data.frame(date,
                       coefLasso)

# Clean up variable names
names(coefLasso) = c('date',
                     'intercept',
                     nameChar)

# Save data frame
saveRDS(coefLasso,
        'coefLasso.RDS')

# Free some memory
rm(weight,
   coefLasso)
