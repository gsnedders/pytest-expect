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

import ast
import os.path
import sys

import pytest
import umsgpack
from six import PY2, PY3, text_type, binary_type

_magic_file_line = b"pytest-expect file v"


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
            config.warn("W1", "failed to load expectation file")


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
            new_type = fp.read(len(_magic_file_line)) == _magic_file_line
            fp.seek(0)
            if new_type:
                self.expect_xfail = self._parse_file(fp)
            else:
                self.expect_xfail = self._parse_legacy_file(fp)

    def _parse_file(self, fp):
        # parse header line
        try:
            line = next(fp)
            if not line.startswith(_magic_file_line):
                raise SyntaxError("invalid pytest-expect file")
            version = int(line[len(_magic_file_line):].rstrip())
        except StopIteration:
            raise SyntaxError("invalid pytest-expect file")

        # parse Python version line
        try:
            line = next(fp)
            if PY3:
                line = line.decode("ascii")
            version_info = ast.literal_eval(line)
            major, minor, micro, releaselevel, serial = version_info
        except (StopIteration, ValueError):
            raise SyntaxError("invalid pytest-expect file")

        # parse the actual file
        if version == 1:
            fails = set()
            for line in fp:
                if PY3:
                    line = line.decode("ascii")
                try:
                    name, result = line.rsplit(":", 1)
                except ValueError:
                    raise SyntaxError("invalid pytest-expect file")
                if result.strip() != "FAIL":
                    raise SyntaxError("invalid pytest-expect file")
                name = ast.literal_eval(name)
                fails.add(name)
                if PY3 and major == 2 and isinstance(name, bytes):
                    try:
                        fails.add(name.decode("latin1"))
                    except UnicodeDecodeError:
                        pass
                if PY2 and major == 3 and isinstance(name, unicode):
                    try:
                        fails.add(name.encode("latin1"))
                    except UnicodeEncodeError:
                        pass
            return fails
        else:
            raise SyntaxError("unknown pytest-expect file version")

    def _raw_make_file(self, fails):
        yield _magic_file_line + b"1\n"
        yield repr(tuple(sys.version_info)) + "\n"
        for fail in sorted(fails):
            r = repr(fail)
            if PY2 and isinstance(fail, str):
                r = "b" + r
            elif PY3 and isinstance(fail, str):
                r = "u" + r
            yield "%s: FAIL\n" % r

    def _make_file(self, fp, fails):
        for line in self._raw_make_file(fails):
            if isinstance(line, text_type):
                line = line.encode("ascii")
            fp.write(line)

    def _parse_legacy_file(self, fp):
        state = umsgpack.unpack(fp)

        if PY3 and b'py_version' in state:
            for key in list(state.keys()):
                state[key.decode("ASCII")] = state[key]
                del state[key]

        version = state["version"]
        py_version = state["py_version"]

        fails = set()

        if version >= 0x0200:
            self.config.warn("W1", "test expectation file in unsupported version")
        elif version >= 0x0100:
            xfail = state["expect_xfail"]
            for s in xfail:
                fails.add(s)
                if PY3 and py_version == 2 and isinstance(s, binary_type):
                    fails.add(s.decode('latin1'))
                elif PY2 and py_version == 3 and isinstance(s, text_type):
                    try:
                        fails.add(s.encode("latin1"))
                    except UnicodeEncodeError:
                        pass
        else:
            self.config.warn("W1", "test expectation file in unsupported version")
        return fails

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
            with open(self.xfail_file, "wb") as fp:
                self._make_file(fp, self.fails)
