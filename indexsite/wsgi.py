"""
WSGI config for indexsite project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/2.0/howto/deployment/wsgi/
"""

# デバッグ用
# import sys
# def application(environ, start_response):
#     status = '200 OK'

#     response_headers = [('Content-type', 'text/plain')]
#     start_response(status, response_headers)
#     version = sys.version
#     return [b"test!!" + version]

#############

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/..' )

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "indexsite.settings")

application = get_wsgi_application()
