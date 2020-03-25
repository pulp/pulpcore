from aiohttp.worker import GunicornWebWorker


class PulpGunicornWebWorker(GunicornWebWorker):

    def _get_application_runner_instance(self, app, **kwargs):
        return super()._get_application_runner_instance(
            app,
            max_line_size=16380,
            max_field_size=16380
        )
