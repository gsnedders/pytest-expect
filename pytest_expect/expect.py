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

import os.path

import pytest
import umsgpack
from six import PY2, PY3, text_type, binary_type


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
    exp = ExpectationPlugin(config)
    config.pluginmanager.register(exp)
    if not exp.update_xfail:
        try:
            exp.load_expectations()
        except:
            self.config.warn("W1", "failed to load expectation file")


class ExpectationPlugin(object):
    def __init__(self, config):
        self.config = config
        self.xfail_file = config.option.xfail_file
        self.update_xfail = config.option.update_xfail
        self.warn_on_python_xfail = config.option.warn_on_python_xfail
        self.fails = set()
        self.expect_xfail = set()

        if self.xfail_file is None:
            self.xfail_file = config.rootdir.join(".pytest.expect").strpath

    def load_expectations(self):
        if not os.path.isfile(self.xfail_file):
            return

        with open(self.xfail_file, "rb") as fp:
            state = umsgpack.unpack(fp)

        if PY3 and b'py_version' in state:
            for key in list(state.keys()):
                state[key.decode("ASCII")] = state[key]
                del state[key]

        version = state["version"]
        py_version = state["py_version"]

        if version >= 0x0200:
            self.expect_xfail = set()
            self.config.warn("W1", "test expectation file in unsupported version")
        elif version >= 0x0100:
            xfail = state["expect_xfail"]
            self.expect_xfail = set()
            for s in xfail:
                self.expect_xfail.add(s)
                if PY3 and py_version == 2 and isinstance(s, binary_type):
                    self.expect_xfail.add(s.decode('latin1'))
                elif PY2 and py_version == 3 and isinstance(s, text_type):
                    try:
                        self.expect_xfail.add(s.encode("latin1"))
                    except UnicodeEncodeError:
                        pass
        else:
            self.expect_xfail = set()
            self.config.warn("W1", "test expectation file in unsupported version")

    def pytest_collectreport(self, report):
        passed = report.outcome in ('passed', 'skipped')
        if passed and not self.update_xfail:
            if report.nodeid in self.expect_xfail:
                self.expect_xfail.remove(report.nodeid)
                for item in report.result:
                    self.expect_xfail.add(item.nodeid)
        elif not passed and self.update_xfail:
            self.fails.add(report.nodeid)

    def pytest_collection_modifyitems(self, session, config, items):
        if not self.update_xfail:
            for item in items:
                if item.nodeid in self.expect_xfail:
                    item.add_marker(pytest.mark.xfail)

    def pytest_runtest_logreport(self, report):
        if self.update_xfail and report.failed and "xfail" not in report.keywords:
            self.fails.add(report.nodeid)

    def pytest_sessionfinish(self, session):
        if (self.update_xfail and
                not hasattr(session.config, 'slaveinput')):
            state = {}
            state["py_version"] = 2 if PY2 else 3
            state["version"] = 0x0100
            state["expect_xfail"] = list(self.fails)
            with open(self.xfail_file, "wb") as fp:
                umsgpack.pack(state, fp)
