from django.conf import settings
from django.http import HttpResponse


PING_PATH = getattr(settings, 'PING_MIDDLEWARE_PATH', '/.ping')


def ping_middleware(get_response):
    def middleware(request):
        if request.path == PING_PATH:
            return HttpResponse('pong', content_type='text/plain')

        return get_response(request)

    return middleware
