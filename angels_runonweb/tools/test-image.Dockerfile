# Odoo image of this project plus Chromium, for the browser tests (hoot suite and the tour
# that runs the real model). The Odoo image is Ubuntu on arm64 here, where Google Chrome has
# no build and apt's chromium is a snap: Playwright's Chromium works on both architectures.
#   docker build -t odoo19-chrome-test:local -f tools/test-image.Dockerfile tools
FROM odoo-odoo
USER root
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw
RUN pip3 install --break-system-packages --no-cache-dir playwright==1.55.0 websocket-client \
    && python3 -m playwright install --with-deps chromium \
    && ln -s "$(find /opt/pw -type f -name chrome -path '*chrome-linux*' | head -1)" /usr/local/bin/chromium \
    && chmod -R a+rX /opt/pw \
    && rm -rf /var/lib/apt/lists/*
USER odoo
