.PHONY: help
help:
	@echo "make [TARGETS...]"
	@echo
	@echo 'Targets:'
	@awk 'match($$0, /^([a-zA-Z_\/-]+):.*? ## (.*)$$/, m) {printf "  \033[36m%-30s\033[0m %s\n", m[1], m[2]}' $(MAKEFILE_LIST) | sort
	@echo
	@echo 'Internal Targets:'
	@awk 'match($$0, /^([a-zA-Z_\/-]+):.*? ### (.*)$$/, m) {printf "  \033[36m%-30s\033[0m %s\n", m[1], m[2]}' $(MAKEFILE_LIST) | sort

GENERATED_MDs=pr_best_practices.md jira_bot.md update_pr.md get_pull_requests.md ai_reasoning.md

%.md: %.py
	python $< --help-md > $@ 2>/dev/null || ( \
	echo '```' > $@ ; \
	python $< --help >> $@ ; \
	echo '```' >>$@ \
	)

GENERATED_SVGs=get_pull_requests.svg ai_reasoning.svg

%.svg: %.puml
	plantuml -tsvg $<

.PHONY: docs
docs: $(GENERATED_MDs) $(GENERATED_SVGs) ## update all generated docs

.PHONY: clean
clean: clean_cache ## clean all generated files
	rm -f $(GENERATED_MDs)
	rm -f $(GENERATED_SVGs)

.PHONY: clean-cache
clean-cache:  ## clean only the caches and debug files
	rm -f test_cache.pkl test_cache.sqlite ai_cache.pkl
	rm -f 03_ai_* 02_similarity_* 01_jira_ai_summary*

.PHONY: check-docs
check-docs: docs  ## check if all docs are up to date or fail otherwise.
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "Error: There are uncommitted changes."; \
		git status --short; \
		exit 1; \
	else \
		echo "Docs seem to be up to date."; \
	fi
