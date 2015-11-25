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
import umsgpack
from six import PY2, PY3, PY34, text_type, binary_type


def pytest_addoption(parser):
    group = parser.getgroup("general")
    group._addoption(
        '--xfail-file',
        action="store", dest="xfail_file", default=None, metavar="FILE",
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
        self.xfail_file = config.option.xfail_file
        self.update_xfail = config.option.update_xfail
        self.warn_on_python_xfail = config.option.warn_on_python_xfail

        if self.xfail_file is None:
            self.xfail_file = config.rootdir.join(".pytest.expect").strpath

        if self.update_xfail:
            self.fails = set()
        else:
            try:
                with open(self.xfail_file, "rb") as fp:
                    if PY3:
                        try:
                            expectations = pickle.load(fp, encoding="bytes")
                        except LookupError:
                            expectations = pickle.load(fp, encoding="latin1")
                    else:
                        expectations = pickle.load(fp)
            except IOError:
                self.to_mark = set()
            except _VersionError:
                config.warn("W1", "test expectation file in unsupported version")
                self.to_mark = set()
            else:
                self.to_mark = expectations.expect_xfail


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

        self.py_version = 2 if PY2 else 3
        self.expect_xfail = expect_xfail

    def __getstate__(self):
        d = copy.copy(self.__dict__)
        d["version"] = 0x0300
        d["expect_xfail"] = list(d["expect_xfail"])
        return umsgpack.packb(d)

    def __setstate__(self, state):
        if isinstance(state, binary_type):
            state = umsgpack.unpackb(state)
        elif isinstance(state, text_type):
            state = umsgpack.unpackb(state.decode('latin1'))

        if PY3 and b'py_version' in state:
            for key in list(state.keys()):
                state[key.decode("ASCII")] = state[key]
                del state[key]

        version = state["version"]
        del state["version"]

        self.__dict__ = state

        if version >= 0x0400:
            raise _VersionError
        elif version >= 0x0300:
            xfail = self.expect_xfail
            self.expect_xfail = set()
            for s in xfail:
                self.expect_xfail.add(s)
                if PY3 and self.py_version == 2 and isinstance(s, binary_type):
                    self.expect_xfail.add(s.decode('latin1'))
                elif PY2 and self.py_version == 3 and isinstance(s, text_type):
                    try:
                        self.expect_xfail.add(s.encode("latin1"))
                    except UnicodeEncodeError:
                        pass
        elif version >= 0x0200:
            xfail = self.expect_xfail
            self.expect_xfail = set()
            for t, s in xfail:
                self.expect_xfail.add(s)
                if PY3 and self.py_version == 2 and t == b'b':
                    if PY34:
                        self.expect_xfail.add(s.decode('latin1'))
                    else:
                        try:
                            self.expect_xfail.add(s.encode("latin1"))
                        except UnicodeEncodeError:
                            pass
                elif PY2 and self.py_version == 3 and t == b'u':
                    try:
                        self.expect_xfail.add(s.encode("latin1"))
                    except UnicodeEncodeError:
                        pass
        elif version >= 0x0100:
            if ((PY3 and not PY34 and self.py_version == 2) or
                (PY2 and self.py_version == 3)):
                for x in copy.copy(self.expect_xfail):
                    if isinstance(x, text_type):
                        try:
                            self.expect_xfail.add(x.encode("latin1"))
                        except UnicodeEncodeError:
                            pass


class _VersionError(Exception):
    pass
