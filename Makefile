SHELL = /bin/bash

.PHONY: release
release:
	bump2version --verbose $${PART:-patch}
	git push
	git push --tags
