# Runs the authors' E-LASSO code unchanged on our input; I/O only.
# Usage: Rscript run_elasso.R <input.parquet> <run_dir> <code_dir>
args = commandArgs(trailingOnly = TRUE)
input = normalizePath(args[1]); runDir = args[2]; codeDir = normalizePath(args[3])
suppressMessages(library(arrow))
d = as.data.frame(read_parquet(input))
d$date = as.Date(d$date)
dir.create(runDir, recursive = TRUE, showWarnings = FALSE)
runDir = normalizePath(runDir)
# The authors' files, copied byte for byte (checksums verified by the caller).
for (f in list.files(codeDir, pattern = '\\.R$', full.names = TRUE)) file.copy(f, runDir, overwrite = TRUE)
setwd(runDir)
# The data file under the name programMainElasso.R expects.
saveRDS(d, 'dataFillCsm1960_2021.RDS')
rm(d)
source('programMainElasso.R')
source('programEvaluateForecast.R')
# Outputs as parquet for the Python judge.
for (n in c('forecastSlasso', 'forecastClasso', 'forecastElasso', 'coefEncompass',
            'coefLasso', 'coefGr', 'statElasso', 'cdmsfeElasso')) {
  x = readRDS(paste0(n, '.RDS'))
  write_parquet(as.data.frame(x), paste0(n, '.parquet'))
}
