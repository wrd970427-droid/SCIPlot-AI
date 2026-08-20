# Install SCIPlot R runtime packages (V0.1 volcano execution).
# Reserved packages are listed but NOT installed yet.

options(
  repos = c(CRAN = "https://cloud.r-project.org"),
  Ncpus = max(1L, parallel::detectCores(logical = TRUE) - 1L)
)

required <- c(
  "tidyverse",
  "ggplot2",
  "ggrepel",
  "svglite",
  "Cairo"
)

# Later figure types (do not install in V0.1):
#   ComplexHeatmap, survival, survminer, pROC, maftools
reserved_not_installed <- c(
  "ComplexHeatmap",
  "survival",
  "survminer",
  "pROC",
  "maftools"
)

install_if_missing <- function(pkg) {
  if (requireNamespace(pkg, quietly = TRUE)) {
    message("already present: ", pkg)
    return(invisible(TRUE))
  }
  install.packages(pkg, dependencies = TRUE)
  if (!requireNamespace(pkg, quietly = TRUE)) {
    stop("failed to install package: ", pkg, call. = FALSE)
  }
  invisible(TRUE)
}

invisible(lapply(required, install_if_missing))

message("SCIPlot V0.1 R packages ready. Reserved (not installed): ",
        paste(reserved_not_installed, collapse = ", "))
