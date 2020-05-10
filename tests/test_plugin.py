import os
import pytest
pytest_plugins = "pytester"

def test_xfail(testdir):
    testdir.makepyfile("""
        def test_one():
            assert True
        
        def test_two():
            assert False
    """)
    # Store the failure in expect file
    result_before_xfail = testdir.runpytest("-vv", "--update-xfail")
    result_before_xfail.assert_outcomes(
        passed=1,
        failed=1
    )

    # Execute the tests
    result = testdir.runpytest("-vv")

    # Assert that the expected failure should be marked xfail
    result.assert_outcomes(
        passed=1,
        xfailed=1
    )
