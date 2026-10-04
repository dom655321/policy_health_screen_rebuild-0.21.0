PY := PYTHONPATH=src python3

.PHONY: test coverage review extract ingest report profile instruments coverage-map export-review catalogue benchmark fixtures verify schema audit golden bless clean statute-rebuild statute-check

test:
	$(PY) -m unittest discover -s tests

coverage:
	$(PY) -m pfia coverage --profile data/profiles/water_authority.json --facts tests/fixtures/facts_water_authority.json

review:
	$(PY) -m pfia review \
		--profile data/profiles/water_authority.json \
		--policy tests/fixtures/policy_conforming.txt \
		--out build/ledger.json

extract:
	$(PY) -m pfia extract \
		--profile data/profiles/water_authority.json \
		--facts tests/fixtures/facts_water_authority.json \
		--policy tests/fixtures/policy_conforming.txt \
		--adapter heuristic --cache .cache/extraction \
		--out build/extraction.json

profile:
	$(PY) -m pfia profile check --profile data/profiles/water_authority.json

instruments:
	$(PY) -m pfia instruments --policy tests/fixtures/policy_conforming.txt

coverage-map:
	$(PY) -m pfia coverage-map --profile data/profiles/water_authority.json

report:
	$(PY) -m pfia review \
		--profile data/profiles/city.json \
		--policy tests/fixtures/policy_deficient.txt \
		--out build/ledger_city.json
	$(PY) -m pfia report \
		--ledger build/ledger_city.json \
		--entity "Example City" --entity-class "Municipality" \
		--out build/report_city.pdf

ingest:
	$(PY) -m pfia ingest --policy tests/fixtures/policy_conforming.pdf

fixtures:
	python3 scripts/make_test_pdf.py

golden:
	python3 scripts/golden.py --check

bless:
	python3 scripts/golden.py --bless

verify:
	python3 scripts/verify_sources.py

schema:
	python3 scripts/validate_schemas.py

clean:
	rm -rf build .cache .pytest_cache **/__pycache__

audit:
	python3 scripts/audit_register.py

export-review:
	python3 scripts/export_review.py --out build/review

benchmark:
	python3 scripts/benchmark.py --truth tests/ground-truth --out build/benchmark

catalogue:
	python3 scripts/export_catalogue.py --out build/catalogue

statute-rebuild:
	python3 scripts/fetch_statute.py --rebuild

statute-check:
	python3 scripts/fetch_statute.py --check
