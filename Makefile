.PHONY: help
help:
	@echo "make [TARGETS...]"
	@echo
	@echo 'Targets:'
	@awk 'match($$0, /^([a-zA-Z_\/-]+):.*? ## (.*)$$/, m) {printf "  \033[36m%-30s\033[0m %s\n", m[1], m[2]}' $(MAKEFILE_LIST) | sort
	@echo
	@echo 'Internal Targets:'
	@awk 'match($$0, /^([a-zA-Z_\/-]+):.*? ### (.*)$$/, m) {printf "  \033[36m%-30s\033[0m %s\n", m[1], m[2]}' $(MAKEFILE_LIST) | sort

GENERATED_MDs=pr_best_practices.md \
 jira_bot.md \
 update_pr.md \
 get_pull_requests.md \
 get_jira_sprint.md

%.md: %.py
	python $< --help-md > $@ 2>/dev/null || ( \
	echo '```' > $@ ; \
	python $< --help >> $@ ; \
	echo '```' >>$@ \
	)

.PHONY: docs
docs: $(GENERATED_MDs) ## update all generated docs

.PHONY: clean
clean: clean-cache ## clean all generated files
	rm -f $(GENERATED_MDs)
	rm -f aws_lambda_main.zip aws_lambda_get_pull_requests.zip
	rm -rf package_main package_get_pull_requests

.PHONY: clean-cache
clean-cache:  ## clean only the caches and debug files
	rm -f test_cache.pkl test_cache.sqlite

.PHONY: check-docs
check-docs: docs  ## check if all docs are up to date or fail otherwise.
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "Error: There are uncommitted changes."; \
		git status --short; \
		exit 1; \
	else \
		echo "Docs seem to be up to date."; \
	fi


.PHONY: build
build: aws_lambda_main.zip aws_lambda_get_pull_requests.zip ## build all AWS Lambda packages
	@echo "AWS Lambda packages built."

# Suggested way by AWS to build the Lambda package
# Somehwat an overkill for one file, but it's consistent with the other package
aws_lambda_main.zip: slack_lambda.py usermap.yaml utils.py requirements_aws_lambda_main.txt
	podman run --rm -v "$(PWD)":/var/task:Z -w /var/task amazonlinux:2 bash -c "\
	yum install -y python3-pip zip && \
	pip3 install --upgrade pip && \
	pip3 install -r requirements_aws_lambda_main.txt -t package_main && \
	cd package_main && \
	zip -r9 ../$@ . && \
	cd .. && \
	zip -g $@ $^"
	@echo "$@ built."

# Suggested way by AWS to build the Lambda package
aws_lambda_get_pull_requests.zip: slack_lambda_get_pull_requests.py utils.py get_pull_requests.py get_jira_sprint.py requirements_aws_lambda_get_pull_requests.txt
	podman run --rm -v "$(PWD)":/var/task:Z -w /var/task amazonlinux:2 bash -c "\
	yum install -y python3-pip zip && \
	pip3 install --upgrade pip && \
	pip3 install -r requirements_aws_lambda_get_pull_requests.txt -t package_get_pull_requests && \
	cd package_get_pull_requests && \
	zip -r9 ../$@ . && \
	cd .. && \
	zip -g $@ $^"
	@echo "$@ built."
