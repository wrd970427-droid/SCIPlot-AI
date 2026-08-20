# SCIPlot AI R runtime — isolated ggplot2/ggrepel/svglite/Cairo environment.
# V0.1: volcano execution only. Do not install extra figure-type packages here.

FROM rocker/r-ver:4.4.2

ENV DEBIAN_FRONTEND=noninteractive \
    R_COMPILE_AND_INSTALL_PACKAGES=never

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        libcurl4-openssl-dev \
        libssl-dev \
        libxml2-dev \
        libcairo2-dev \
        libxt-dev \
        libpng-dev \
        libjpeg-dev \
        libtiff5-dev \
        libfreetype6-dev \
        libfontconfig1-dev \
        libharfbuzz-dev \
        libfribidi-dev \
        libgit2-dev \
    && rm -rf /var/lib/apt/lists/*

COPY R/packages.R /tmp/packages.R
RUN Rscript /tmp/packages.R && rm -f /tmp/packages.R

RUN useradd --uid 1000 --create-home --home-dir /home/sciplot \
        --shell /usr/sbin/nologin sciplot \
    && mkdir -p /in /out \
    && chown sciplot:sciplot /out

USER sciplot
WORKDIR /out

# Scripts are provided at runtime as read-only /in/script.R
# Figures must be written only to /out.
CMD ["Rscript", "--vanilla", "/in/script.R"]
