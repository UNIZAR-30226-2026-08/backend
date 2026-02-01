"""
ASGI config for magnate project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import magnate.routing 

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'magnate.settings')

application = ProtocolTypeRouter({
    # Normal HTTP requests are handled by Django
    "http": get_asgi_application(),
    
    # Websocket requests are handled by Channels
    "websocket": AuthMiddlewareStack(
        URLRouter(
            magnate.routing.websocket_urlpatterns
        )
    ),
})