"""py.test plugin to store test expectations

Stores test expectations by storing the set of failing tests, allowing
them to be marked as xfail when running them in future. The tests
expectations are stored such that they can be distributed alongside
the tests. However, note that test expectations can only be reliably
shared between Python 2 and Python 3 if they only use ASCII characters
in their node ids: this likely isn't a limitation if tests are using
the normal Python format, as Python 2 only allows ASCII characters in
identifiers.
"""

import copy
import pickle
import pickletools
import sys

import pytest

PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3


def pytest_addoption(parser):
    group = parser.getgroup("general")
    group._addoption(
        '--xfail-file',
        action="store", dest="xfail_file", default=".pytest.expect", metavar="FILE",
        help="store test expectations in FILE"
    )

    group._addoption(
        "--update-xfail",
        action="store_true", dest="update_xfail", default=False,
        help="rebaseline test expectations with current failing tests"
    )

    group.addoption(
        "--warn-on-python-xfail",
        action="store_true", dest="warn_on_python_xfail", default=False,
        help="trigger a warning when a Python test fails"
    )


def pytest_configure(config):
    config.pluginmanager.register(ExpectationPlugin(config))


class ExpectationPlugin(object):
    def __init__(self, config):
        self.xfail_file = config.rootdir.join(config.option.xfail_file).strpath
        self.update_xfail = config.option.update_xfail
        self.warn_on_python_xfail = config.option.warn_on_python_xfail

        if self.update_xfail:
            self.fails = set()
        else:
            try:
                with open(self.xfail_file, "rb") as fp:
                    if PY3:
                        expectations = pickle.load(fp, encoding="bytes")
                    else:
                        expectations = pickle.load(fp)
            except IOError:
                self.to_mark = set()
            except _VersionError:
                self.config.warn("W1", "test expectation file in unsupported version")
                self.to_mark = set()
            else:
                self.to_mark = expectations.expect_xfail
                if expectations.py_version != sys.version_info[0]:
                    self._adjust_to_mark_for_python_version()

    def _adjust_to_mark_for_python_version(self):
        """A somewhat evil hack to try and get as many node ids working Python versions"""
        if PY3:
            for nodeid in copy.copy(self.to_mark):
                if isinstance(nodeid, bytes):
                    try:
                        self.to_mark.add(nodeid.decode("utf-8"))
                    except UnicodeEncodeError:
                        pass
        else:
            assert PY2
            for nodeid in copy.copy(self.to_mark):
                if isinstance(nodeid, unicode):
                    try:
                        self.to_mark.add(nodeid.encode("utf-8"))
                    except UnicodeDecodeError:
                        pass

    def pytest_collectreport(self, report):
        passed = report.outcome in ('passed', 'skipped')
        if passed and not self.update_xfail:
            if report.nodeid in self.to_mark:
                self.to_mark.remove(report.nodeid)
                for item in report.result:
                    self.to_mark.add(item.nodeid)
        elif not passed and self.update_xfail:
            self.fails.add(report.nodeid)

    def pytest_collection_modifyitems(self, session, config, items):
        if not self.update_xfail:
            for item in items:
                if item.nodeid in self.to_mark:
                    item.add_marker(pytest.mark.xfail)

    def pytest_runtest_logreport(self, report):
        if self.update_xfail and report.failed and "xfail" not in report.keywords:
            self.fails.add(report.nodeid)

    def pytest_sessionfinish(self, session):
        if self.update_xfail and not hasattr(session.config, 'slaveinput'):
            expectation = _Expectations(self.fails)
            pickled = pickle.dumps(expectation, protocol=2)
            with open(self.xfail_file, "wb") as fp:
                fp.write(pickletools.optimize(pickled))


class _Expectations(object):
    def __init__(self, expect_xfail):
        assert isinstance(expect_xfail, set)

        self.version = 0x0100
        self.py_version = 2 if PY2 else 3
        self.expect_xfail = expect_xfail

    def __getstate__(self):
        return self.__dict__

    def __setstate__(self, state):
        if PY3 and state[b'py_version'] == 2:
            for key in list(state.keys()):
                state[key.decode("ASCII")] = state[key]
                del state[key]

        self.__dict__ = state
        if self.version >= 0x0200:
            raise _VersionError


class _VersionError(Exception):
    pass
