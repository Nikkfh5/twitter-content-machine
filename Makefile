.PHONY: test doctor

test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q

doctor:
	python -m twitter_content_machine doctor
