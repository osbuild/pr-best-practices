.PHONY: help
help:
	@echo "make [TARGETS...]"
	@echo
	@echo 'Targets:'
	@awk 'match($$0, /^([a-zA-Z_\/-]+):.*? ## (.*)$$/, m) {printf "  \033[36m%-30s\033[0m %s\n", m[1], m[2]}' $(MAKEFILE_LIST) | sort
	@echo
	@echo 'Internal Targets:'
	@awk 'match($$0, /^([a-zA-Z_\/-]+):.*? ### (.*)$$/, m) {printf "  \033[36m%-30s\033[0m %s\n", m[1], m[2]}' $(MAKEFILE_LIST) | sort

GENERATED_MDs=pr_best_practices.md jira_bot.md update_pr.md get_pull_requests.md

%.md: %.py
	python $< --help-md > $@ 2>/dev/null || ( \
	echo '```' > $@ ; \
	python $< --help >> $@ ; \
	echo '```' >>$@ \
	)

.PHONY: docs
docs: $(GENERATED_MDs) ## update all generated docs

.PHONY: clean
clean:  ## clean all generated files
	rm -f $(GENERATED_MDs)

.PHONY: check-docs
check-docs: docs  ## check if all docs are up to date or fail otherwise.
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "Error: There are uncommitted changes."; \
		git status --short; \
		exit 1; \
	else \
		echo "Docs seem to be up to date."; \
	fi
