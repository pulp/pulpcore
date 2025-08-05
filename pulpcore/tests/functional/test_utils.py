import pytest
from pulpcore.tests.functional.utils import IpcUtil


class TestIpcUtil:

    def test_catch_subprocess_errors(self):

        def host_act(host_turn, log):
            with host_turn():
                log.put(0)

        def child_act(child_turn, log):
            with child_turn():
                log.put(1)
                assert 1 == 0

        error_msg = "AssertionError: assert 1 == 0"
        with pytest.raises(Exception, match=error_msg):
            IpcUtil.run(host_act, child_act)

    def test_turns_are_deterministic(self):
        RUNS = 1000
        errors = 0

        def host_act(host_turn, log):
            with host_turn():
                log.put(0)

            with host_turn():
                log.put(2)

            with host_turn():
                log.put(4)

        def child_act(child_turn, log):
            with child_turn():
                log.put(1)

            with child_turn():
                log.put(3)

            with child_turn():
                log.put(5)

        def run():
            log = IpcUtil.run(host_act, child_act)
            if log != [0, 1, 2, 3, 4, 5]:
                return 1
            return 0

        for _ in range(RUNS):
            errors += run()

        error_rate = errors / RUNS
        assert error_rate == 0
