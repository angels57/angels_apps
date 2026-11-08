# angels_runonweb tools

Nothing here runs inside Odoo.

## Rebuild the library

`static/lib/runonweb` is generated from the pinned `runonweb` package. To change its
version or add a task entry in `entries/`:

```bash
cd modules/angels_runonweb/tools
npm ci && npm run build
rm -rf node_modules   # 600 MB; keep the addon folder light
```

A new task also needs its files (path, size, SHA-256) in `utils/catalog.py`, an entry in
`static/src/core/loader.js` and a lab panel in `static/src/lab/lab_tasks.js`.

## Run the tests

The browser tests need Chromium, which the Odoo image does not have. Build the test image
once, then run the tests on a separate database (`test_runonweb`), with a data volume of
its own:

```bash
docker build -t odoo19-chrome-test:local -f modules/angels_runonweb/tools/test-image.Dockerfile modules/angels_runonweb/tools
docker volume create angels_runonweb_testdata

RUN="docker run --rm -i --network odoo_default \
  -v $PWD/config/odoo.docker.conf:/etc/odoo/odoo.conf:ro \
  -v $PWD/modules:/mnt/extra-addons \
  -v angels_runonweb_testdata:/var/lib/odoo odoo19-chrome-test:local"

# First time: create the database, then fill the model cache of the end-to-end test
# (tests cannot reach the internet).
$RUN odoo -c /etc/odoo/odoo.conf -d test_runonweb -i angels_runonweb --stop-after-init
$RUN odoo shell -c /etc/odoo/odoo.conf -d test_runonweb --no-http < modules/angels_runonweb/tools/seed_test_cache.py

# Every run
$RUN odoo -c /etc/odoo/odoo.conf -d test_runonweb -u angels_runonweb \
  --test-tags /angels_runonweb --stop-after-init
```

| Test | What it covers |
|---|---|
| `test_storage.py` | Catalog pinning, download with size and SHA-256 checks, atomic writes |
| `test_runonweb.py` | Config, admin-only actions, download/remove, settings, Spanish catalog |
| `test_routes.py` | Allowlisted public routes, 404s, redirect only when allowed, cache headers |
| `test_browser.py` | Hoot suite (`static/tests/*.test.js`) and the tour that runs text2emoji-tiny in Chromium with no request leaving Odoo |
