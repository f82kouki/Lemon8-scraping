PYTHON ?= python3

URLS_FILE ?= Lemon8/tests/runtime/urls.txt
LINKED_ACCOUNTS_FILE ?= Lemon8/tests/runtime/linked_accounts.json
LINKED_ACCOUNTS_MULTI_FILE ?= Lemon8/tests/runtime/linked_accounts_multi.json
URL_USER_MAPPING_FILE ?= Lemon8/tests/runtime/url_user_mapping.csv
OUTPUT_JSONL ?= Lemon8/tests/runtime/validation_result.jsonl
OUTPUT_JSONL_MULTI ?= Lemon8/tests/runtime/validation_result_multi.jsonl
LOG_FILE ?= Lemon8/tests/runtime/validation_debug.log
REGION ?= jp
ALLOWED_REGIONS ?= jp

.PHONY: install test validate validate-verbose validate-multi validate-multi-default vm

install:
	$(PYTHON) -m pip install --user pytest httpx beautifulsoup4

test:
	$(PYTHON) -m pytest Lemon8/tests

validate:
	$(PYTHON) -m Lemon8.poc.run_validation \
		--mode single_user \
		--urls-file "$(URLS_FILE)" \
		--linked-accounts-file "$(LINKED_ACCOUNTS_FILE)" \
		--output-jsonl "$(OUTPUT_JSONL)" \
		--region "$(REGION)" \
		--allowed-regions "$(ALLOWED_REGIONS)"

validate-verbose:
	$(PYTHON) -m Lemon8.poc.run_validation \
		--mode single_user \
		--urls-file "$(URLS_FILE)" \
		--linked-accounts-file "$(LINKED_ACCOUNTS_FILE)" \
		--output-jsonl "$(OUTPUT_JSONL)" \
		--region "$(REGION)" \
		--allowed-regions "$(ALLOWED_REGIONS)" \
		--verbose \
		--log-file "$(LOG_FILE)"

validate-multi:
	@test -f "$(URL_USER_MAPPING_FILE)" || (echo "Missing mapping file: $(URL_USER_MAPPING_FILE)"; echo "Usage: make validate-multi URL_USER_MAPPING_FILE=path/to/url_user_mapping.csv LINKED_ACCOUNTS_FILE=path/to/linked_accounts_multi.json"; exit 1)
	$(PYTHON) -m Lemon8.poc.run_validation \
		--mode multi_user \
		--urls-file "$(URLS_FILE)" \
		--linked-accounts-file "$(LINKED_ACCOUNTS_FILE)" \
		--url-user-mapping-file "$(URL_USER_MAPPING_FILE)" \
		--output-jsonl "$(OUTPUT_JSONL_MULTI)" \
		--region "$(REGION)" \
		--allowed-regions "$(ALLOWED_REGIONS)"

# Multi-user quick run with default runtime files.
validate-multi-default:
	@$(MAKE) validate-multi LINKED_ACCOUNTS_FILE="$(LINKED_ACCOUNTS_MULTI_FILE)" URL_USER_MAPPING_FILE="$(URL_USER_MAPPING_FILE)"

# Super short alias for multi-user validation.
vm: validate-multi-default
