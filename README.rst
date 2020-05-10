pytest-expect
=============

A `py.test <http://pytest.org/latest/>`_ plugin that stores test
expectations by saving the set of failing tests, allowing them to be
marked as xfail when running them in future. The tests expectations
are stored such that they can be distributed alongside the
tests. However, note that test expectations can only be reliably
shared between Python 2 and Python 3 if they only use ASCII characters
in their node ids: this likely isn't a limitation if tests are using
the normal Python format, as Python 2 only allows ASCII characters in
identifiers.

Installation
------------
.. code-block:: console

   pip install pytest-expect

How to use
----------

**Expect file name**

* Default name of the xfail-file is ``.pytest.expect``.
* To customize the name of the xfail-file, use pytest parameter ``--xfail-file <File_Name>``.

**Store the test failures to a file.**

Use ``update-xfail`` parameter. The ``.pytest.expect`` file should be created after the test session is finished.

.. code-block:: console

     >> pytest -vv --update-xfail
     . . .
     test_one.py::test_one PASSED   [ 50%]
     test_one.py::test_two FAILED   [100%]
     . . .

**Apply expect file to a test session**

Once, the xfail-file is created, it will be picked by the module to mark the expected failure as XFAIL. With the XFAIL failures only, the test report will turn green.

.. code-block:: console

   >> pytest -vv
   . . .
   test_one.py::test_one PASSED   [ 50%]
   test_one.py::test_two XFAIL    [100%]
   . . .

**Example with custom xfail-file**

.. code-block:: console

     >> pytest -vv --xfail-file custom_file --update-xfail
     . . .
     test_one.py::test_one PASSED   [ 50%]
     test_one.py::test_two FAILED   [100%]
     . . .

     >> pytest -vv --xfail-file custom_file
     . . .
     test_one.py::test_one PASSED   [ 50%]
     test_one.py::test_two XFAIL    [100%]
     . . .


Compatibility
-------------

We follow `semver <http://semver.org/spec/v2.0.0.html>`_. Our public
API is defined by the expectation file and the command line parameters.

In other words: for a given major release (e.g., 1.y.z), expectation
files and command line parameters will remain compatible. Across major
versions, we'll try to break as little as possible. All pre-release
(0.y.z) versions should be compatible with each other, but are
unlikely to be compatible with 1.0.0.

