############################
# programMainElasso.R
#
# Last modified: 13-Jun-2024
############################

# Start time
timeStart = Sys.time()

###############
# Load packages
###############

library(glmnet)
library(rlist)
library(parallel)

########################################
# Load data & take care of preliminaries
########################################

# Data file (data frame in RDS file)
nameDataFile = 'dataFillCsm1960_2021.RDS'

# Load data file
data = readRDS(nameDataFile)

# The following names should be used for the first five variables that must be
# included in the data frame:
# date: 'date'
# firm identifier: 'permno'
# exchange code: exchcd
# market equity: 'me'
# return: 'ret'

# Names - non-characteristic variables in the data frame (should be the first
# five variables appearing in the data frame in this order, followed by
# variables corresponding to the characteristics/predictors)
nameFront = c('date',
              'permno',
              'exchcd',
              'me',
              'ret')

# Characteristic names
nameChar = names(data)[ -(1:length(nameFront)) ]

# Number of characteristics
J = length(nameChar)

# If returns are in decimal notation, then change to percent
data$ret = 100*data$ret

# Extract date vector
date = unique(data$date)

# Number of time-series observations
T = length(date)

# Smoothing window lengths
vecSizeMa = c(1,
              36,
              60,
              120,
              Inf)

# Names - smoothing window lengths
nameSizeMa = paste0('Ma',
                    vecSizeMa)

# Number of cores - mclapply argument (parallel computing)
coreNumber = 16

##########################
# Step 1: S-LASSO forecast
##########################

cat('Compute LASSO coefficients\n\n')

# Generate/save coefLasso.RDS
source('programCoefLasso.R')

cat('Compute S-LASSO forecast\n\n')

# Generate/save forecastSlasso.RDS
source('programForecastSlasso.R')

##########################
# Step 2: C-LASSO forecast
##########################

cat('Compute univariate coefficients\n\n')

# Generate/save coefUniIntercept.RDS/coefUniSlope.RDS
source('programCoefUni.R')

cat('Compute univariate forecasts\n\n')

# Generate/save forecastUni.RDS
source('programForecastUni.R')

cat('Compute C-LASSO forecast\n\n')

# Generate/save coefGr.RDS/forecastClasso.RDS
source('programForecastClasso.R')

##########################
# Step 3: E-LASSO forecast
##########################

cat('Compute E-LASSO forecast\n\n')

# Generate/save coefEncompass.RDS/forecastElasso.RDS
source('programForecastElasso.R')

# End time
timeEnd = Sys.time()

# Time elapsed
timeTaken = round(timeEnd - timeStart, 2)

cat('Time elapsed (in minutes) =', timeTaken, '\n\n')
