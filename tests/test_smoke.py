def test_release_module_imports(release_module):
    assert hasattr(release_module, "run")
